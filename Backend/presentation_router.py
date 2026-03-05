from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/presentation", tags=["Presentation"])

DEFAULT_PRESENTON_BASE_URL = os.getenv("PRESENTON_BASE_URL", "http://127.0.0.1:5000").strip()
DEFAULT_PRESENTON_API_KEY = os.getenv("PRESENTON_API_KEY", "").strip()

LOCAL_GENERATE_PATH = os.getenv("PRESENTON_LOCAL_PATH", "/api/v1/ppt/presentation/generate").strip()
CLOUD_SYNC_PATH = os.getenv("PRESENTON_SYNC_PATH", "/api/v1/ppt/presentation/generate/sync").strip()
CLOUD_ASYNC_PATH = os.getenv("PRESENTON_ASYNC_PATH", "/api/v1/ppt/presentation/generate/async").strip()
STATUS_PATH_TEMPLATE = os.getenv("PRESENTON_STATUS_PATH_TEMPLATE", "/api/v1/ppt/presentation/status/{task_id}").strip()

REQUEST_TIMEOUT_SEC = float(os.getenv("PRESENTON_REQUEST_TIMEOUT_SEC", "180"))
POLL_TIMEOUT_SEC = float(os.getenv("PRESENTON_POLL_TIMEOUT_SEC", "900"))
POLL_INTERVAL_SEC = float(os.getenv("PRESENTON_POLL_INTERVAL_SEC", "2"))
INVALID_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
PRESENTON_PROXY_PREFIX = "/api/presentation/presenton/proxy"
PRESENTON_USER_CONFIG_PATH = os.getenv("PRESENTON_USER_CONFIG_PATH", "/api/user-config").strip() or "/api/user-config"
PPT_RUNTIME_MODEL = os.getenv("PRESENTON_PPT_RUNTIME_MODEL", "qwen3:1.7b").strip() or "qwen3:1.7b"
PPT_RESTORE_MODEL = os.getenv("PRESENTON_PPT_RESTORE_MODEL", "qwen2.5-coder:latest").strip() or "qwen2.5-coder:latest"
PPT_MODEL_KEEP_ALIVE = os.getenv("PRESENTON_PPT_MODEL_KEEP_ALIVE", "1h").strip() or "1h"
OLLAMA_CONTROL_URL = (
    os.getenv("PRESENTON_OLLAMA_CONTROL_URL")
    or os.getenv("OLLAMA_API_BASE")
    or "http://127.0.0.1:11434"
).strip().rstrip("/")
OLLAMA_CONTROL_TIMEOUT_SEC = float(os.getenv("PRESENTON_OLLAMA_CONTROL_TIMEOUT_SEC", "30"))
PPT_TASK_STALE_SEC = float(os.getenv("PRESENTON_PPT_TASK_STALE_SEC", "7200"))
TERMINAL_TASK_STATUSES = {"completed", "done", "success", "succeeded", "failed", "error", "cancelled", "canceled"}
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
PROXY_REWRITE_CONTENT_TYPES = ("text/html", "javascript", "text/css", "application/json")
LOCAL_HOST_CANDIDATES = {"127.0.0.1", "localhost", "0.0.0.0", "host.docker.internal"}
ROOT_RELATIVE_REF_RE = re.compile(
    rf"([\"'])/(?!/|{re.escape(PRESENTON_PROXY_PREFIX.lstrip('/'))})(?=[A-Za-z0-9._~%?-])([^\"']*)"
)

_PRESENTON_SESSION = requests.Session()
_PRESENTON_SESSION.mount("http://", HTTPAdapter(pool_connections=32, pool_maxsize=128, max_retries=0))
_PRESENTON_SESSION.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=128, max_retries=0))
_MODEL_RUNTIME_LOCK = threading.Lock()
_ACTIVE_PPT_TASKS: Dict[str, float] = {}
logger = logging.getLogger(__name__)


class PresentonGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=4, max_length=12000, description="PPT 生成提示词")
    n_slides: int = Field(default=10, ge=3, le=40, description="页数")
    language: str = Field(default="Chinese", max_length=64)
    template: str = Field(default="general", max_length=64)
    export_as: str = Field(default="pptx", max_length=16)
    tone: str = Field(default="professional", max_length=32)
    verbosity: str = Field(default="standard", max_length=32)
    provider: Literal["auto", "local", "cloud_sync", "cloud_async"] = "auto"
    base_url: Optional[str] = None


def _normalize_base_url(base_url: Optional[str]) -> str:
    raw = (base_url or DEFAULT_PRESENTON_BASE_URL or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="Presenton base URL is not configured")
    return raw.rstrip("/")


def _build_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if DEFAULT_PRESENTON_API_KEY:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"
    return headers


def _normalize_model_name(model_name: Optional[str]) -> str:
    value = str(model_name or "").strip().lower()
    if not value:
        return ""
    return value if ":" in value else f"{value}:latest"


def _is_same_model(model_a: Optional[str], model_b: Optional[str]) -> bool:
    a = _normalize_model_name(model_a)
    b = _normalize_model_name(model_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.removesuffix(":latest") == b.removesuffix(":latest")


def _ollama_request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not OLLAMA_CONTROL_URL:
        raise HTTPException(status_code=500, detail="OLLAMA control URL is not configured")
    endpoint = f"{OLLAMA_CONTROL_URL}{path}"
    try:
        response = _PRESENTON_SESSION.request(
            method=method,
            url=endpoint,
            json=payload,
            timeout=OLLAMA_CONTROL_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Ollama control request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except Exception:
        data = {"raw_text": raw_text[:1200]}

    if response.status_code >= 400:
        detail = data.get("error") or data.get("message") or data.get("detail") or data.get("raw_text")
        raise HTTPException(status_code=502, detail=f"Ollama control error ({response.status_code}): {detail}")
    return data


def _list_loaded_ollama_models() -> List[str]:
    data = _ollama_request_json("GET", "/api/ps")
    models = data.get("models")
    if not isinstance(models, list):
        return []
    result: List[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        candidate = item.get("name") or item.get("model")
        if candidate:
            result.append(str(candidate))
    return result


def _set_presenton_ollama_model(base_url: str, model_name: str) -> None:
    payload = {
        "LLM": "ollama",
        "OLLAMA_MODEL": model_name,
    }
    _request_json(
        "POST",
        f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
        {"Content-Type": "application/json"},
        payload=payload,
        timeout=max(REQUEST_TIMEOUT_SEC, 30),
    )


def _unload_ollama_model(model_name: str) -> None:
    _ollama_request_json(
        "POST",
        "/api/generate",
        payload={
            "model": model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        },
    )


def _warmup_ollama_model(model_name: str) -> None:
    _ollama_request_json(
        "POST",
        "/api/generate",
        payload={
            "model": model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": PPT_MODEL_KEEP_ALIVE,
        },
    )


def _ensure_only_ollama_model(target_model: str) -> None:
    # Keep only one mounted model in memory to avoid cross-model contention during PPT generation.
    loaded_before = _list_loaded_ollama_models()
    for model_name in loaded_before:
        if _is_same_model(model_name, target_model):
            continue
        try:
            _unload_ollama_model(model_name)
        except HTTPException as exc:
            logger.warning("Failed to unload model %s: %s", model_name, exc.detail)

    loaded_mid = _list_loaded_ollama_models()
    if not any(_is_same_model(item, target_model) for item in loaded_mid):
        _warmup_ollama_model(target_model)

    loaded_after = _list_loaded_ollama_models()
    for model_name in loaded_after:
        if _is_same_model(model_name, target_model):
            continue
        try:
            _unload_ollama_model(model_name)
        except HTTPException as exc:
            logger.warning("Second-pass unload failed for model %s: %s", model_name, exc.detail)


def _activate_ppt_runtime(base_url: str) -> None:
    _set_presenton_ollama_model(base_url, PPT_RUNTIME_MODEL)
    _ensure_only_ollama_model(PPT_RUNTIME_MODEL)


def _restore_default_runtime(base_url: str) -> None:
    _set_presenton_ollama_model(base_url, PPT_RESTORE_MODEL)
    _ensure_only_ollama_model(PPT_RESTORE_MODEL)


def _purge_stale_tasks_locked(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    stale_ids = [task_id for task_id, ts in _ACTIVE_PPT_TASKS.items() if (now - ts) > PPT_TASK_STALE_SEC]
    for task_id in stale_ids:
        _ACTIVE_PPT_TASKS.pop(task_id, None)


def _join_url(base_url: str, path_or_url: Optional[str]) -> Optional[str]:
    if path_or_url is None:
        return None
    value = str(path_or_url).strip()
    if not value:
        return None
    safe_value = INVALID_PERCENT_RE.sub("%25", value)
    if safe_value.startswith("http://") or safe_value.startswith("https://"):
        return requests.utils.requote_uri(safe_value)
    if safe_value.startswith("/"):
        return requests.utils.requote_uri(f"{base_url}{safe_value}")
    return requests.utils.requote_uri(f"{base_url}/{safe_value}")


def _extract_task_id(payload: Dict[str, Any]) -> Optional[str]:
    candidates = [
        payload.get("task_id"),
        payload.get("request_id"),
        payload.get("id"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("task_id"), data.get("request_id"), data.get("id")])
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _extract_urls(payload: Dict[str, Any], base_url: str) -> Tuple[Optional[str], Optional[str]]:
    data = payload.get("data")
    nested: Dict[str, Any] = data if isinstance(data, dict) else {}

    download_candidates = [
        payload.get("download_url"),
        payload.get("file_url"),
        payload.get("url"),
        payload.get("path"),
        payload.get("pptx_url"),
        nested.get("download_url"),
        nested.get("file_url"),
        nested.get("url"),
        nested.get("path"),
        nested.get("pptx_url"),
    ]
    edit_candidates = [
        payload.get("edit_url"),
        payload.get("edit_path"),
        nested.get("edit_url"),
        nested.get("edit_path"),
    ]

    download_url = next((_join_url(base_url, item) for item in download_candidates if _join_url(base_url, item)), None)
    edit_url = next((_join_url(base_url, item) for item in edit_candidates if _join_url(base_url, item)), None)
    return download_url, edit_url


def _is_same_origin(url: str, expected_base_url: str) -> bool:
    target = urlparse(url)
    expected = urlparse(expected_base_url)
    return (
        target.scheme.lower() == expected.scheme.lower()
        and target.hostname == expected.hostname
        and (target.port or (443 if target.scheme == "https" else 80))
        == (expected.port or (443 if expected.scheme == "https" else 80))
    )


def _build_download_proxy_url(download_url: Optional[str]) -> Optional[str]:
    if not download_url:
        return None
    return f"/api/presentation/presenton/download?target={quote(download_url, safe='')}"


def _build_presenton_proxy_url(target_url: Optional[str], base_url: str) -> Optional[str]:
    normalized = _join_url(base_url, target_url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{PRESENTON_PROXY_PREFIX}{path}{query}"


def _decorate_result_urls(result: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    raw_download = result.get("download_url")
    raw_edit = result.get("edit_url")
    proxied_download = _build_download_proxy_url(raw_download)
    proxied_edit = _build_presenton_proxy_url(raw_edit, base_url)
    decorated = dict(result)
    if raw_download:
        decorated["download_url_raw"] = raw_download
    if raw_edit:
        decorated["edit_url_raw"] = raw_edit
    if proxied_download:
        decorated["download_url"] = proxied_download
    if proxied_edit:
        decorated["edit_url"] = proxied_edit
    return decorated


def _estimate_progress(status: str, message: str) -> int:
    status_l = str(status or "").lower()
    message_l = str(message or "").lower()
    if status_l in {"completed", "done", "success", "succeeded"}:
        return 100
    if "outline" in message_l:
        return 20
    if "layout" in message_l:
        return 40
    if "generating slide" in message_l or "generating slides" in message_l:
        return 68
    if "fetching asset" in message_l:
        return 88
    if "saving" in message_l or "export" in message_l:
        return 95
    return 10 if status_l == "pending" else 0


def _coerce_progress_value(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 1:
        numeric *= 100
    return int(max(0, min(100, round(numeric))))


def _extract_progress_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    direct_keys = ("progress", "percentage", "percent", "completion")
    for key in direct_keys:
        if key in payload:
            coerced = _coerce_progress_value(payload.get(key))
            if coerced is not None:
                return coerced

    data = payload.get("data")
    if isinstance(data, dict):
        for key in direct_keys:
            if key in data:
                coerced = _coerce_progress_value(data.get(key))
                if coerced is not None:
                    return coerced

    message = str(payload.get("message") or "")
    ratio_match = None
    if message:
        import re

        percent_match = re.search(r"(\d{1,3})\s*%", message)
        if percent_match:
            coerced = _coerce_progress_value(percent_match.group(1))
            if coerced is not None:
                return coerced
        ratio_match = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", message)
    if ratio_match:
        done = float(ratio_match.group(1))
        total = float(ratio_match.group(2))
        if total > 0:
            return _coerce_progress_value(done / total)
    return None


def _rewrite_presenton_text_payload(content: str, base_url: str) -> str:
    # Rewrite both absolute local URLs and root-relative refs so all assets/APIs stay in backend proxy.
    parsed_base = urlparse(base_url)
    host_candidates = set(LOCAL_HOST_CANDIDATES)
    if parsed_base.hostname:
        host_candidates.add(parsed_base.hostname.lower())
    host_pattern = "|".join(sorted((re.escape(host) for host in host_candidates), key=len, reverse=True))
    absolute_local_ref_re = re.compile(
        rf"https?://(?:{host_pattern})(?::\d+)?(?P<path>/[^\s\"'<>]*)?"
    )

    rewritten = absolute_local_ref_re.sub(
        lambda match: f"{PRESENTON_PROXY_PREFIX}{match.group('path') or '/'}",
        content,
    )
    rewritten = ROOT_RELATIVE_REF_RE.sub(
        lambda match: f"{match.group(1)}{PRESENTON_PROXY_PREFIX}/{match.group(2)}",
        rewritten,
    )
    return rewritten


def _build_proxy_upstream_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length"}:
            continue
        headers[key] = value
    if DEFAULT_PRESENTON_API_KEY and "authorization" not in {k.lower() for k in headers}:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"
    return headers


def _filter_proxy_response_headers(headers: Dict[str, str], base_url: str) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS:
            continue
        if lowered in {"content-security-policy", "content-length", "content-encoding"}:
            continue
        if lowered == "location":
            proxied_location = _build_presenton_proxy_url(value, base_url)
            filtered[key] = proxied_location or value
            continue
        filtered[key] = value
    return filtered


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = REQUEST_TIMEOUT_SEC,
) -> Dict[str, Any]:
    try:
        response = _PRESENTON_SESSION.request(method=method, url=url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Presenton request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except Exception:
        data = {"raw_text": raw_text[:2000]}

    if response.status_code >= 400:
        detail = (
            data.get("message")
            or data.get("error")
            or data.get("detail")
            or data.get("raw_text")
            or f"Presenton API error ({response.status_code})"
        )
        raise HTTPException(status_code=502, detail=str(detail))
    return data


def _build_generation_payload(req: PresentonGenerateRequest) -> Dict[str, Any]:
    return {
        "prompt": req.prompt,
        "content": req.prompt,
        "instructions": req.prompt,
        "n_slides": req.n_slides,
        "language": req.language,
        "template": req.template,
        "export_as": req.export_as,
        "tone": req.tone,
        "verbosity": req.verbosity,
    }


def _generate_local(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    url = f"{base_url}{LOCAL_GENERATE_PATH}"
    data = _request_json("POST", url, headers, payload)
    download_url, edit_url = _extract_urls(data, base_url)
    return {
        "success": True,
        "provider": "local",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": _extract_task_id(data),
        "raw": data,
    }


def _generate_cloud_sync(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    url = f"{base_url}{CLOUD_SYNC_PATH}"
    data = _request_json("POST", url, headers, payload, timeout=max(REQUEST_TIMEOUT_SEC, POLL_TIMEOUT_SEC))
    download_url, edit_url = _extract_urls(data, base_url)
    return {
        "success": True,
        "provider": "cloud_sync",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": _extract_task_id(data),
        "raw": data,
    }


def _poll_cloud_status(base_url: str, headers: Dict[str, str], task_id: str) -> Dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SEC

    latest: Dict[str, Any] = {}
    while time.time() < deadline:
        latest = _fetch_cloud_status(base_url, headers, task_id)
        status_value = str(latest.get("status") or "").lower()
        if status_value in {"completed", "done", "success", "succeeded"}:
            return latest
        if status_value in {"failed", "error", "cancelled", "canceled"}:
            detail = latest.get("message") or latest.get("error") or "Presenton task failed"
            raise HTTPException(status_code=502, detail=str(detail))
        time.sleep(max(0.2, POLL_INTERVAL_SEC))

    raise HTTPException(status_code=504, detail="Presenton task polling timeout")


def _fetch_cloud_status(base_url: str, headers: Dict[str, str], task_id: str) -> Dict[str, Any]:
    status_path = STATUS_PATH_TEMPLATE.replace("{task_id}", task_id)
    status_url = f"{base_url}{status_path}"
    return _request_json("GET", status_url, headers, payload=None)


def _generate_cloud_async(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    submit_url = f"{base_url}{CLOUD_ASYNC_PATH}"
    submit_data = _request_json("POST", submit_url, headers, payload)
    task_id = _extract_task_id(submit_data)
    if not task_id:
        raise HTTPException(status_code=502, detail="Presenton did not return task id")

    final_data = _poll_cloud_status(base_url, headers, task_id)
    download_url, edit_url = _extract_urls(final_data, base_url)
    return {
        "success": True,
        "provider": "cloud_async",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": task_id,
        "raw": final_data,
    }


@router.post("/presenton/generate")
def generate_presenton_ppt(req: PresentonGenerateRequest):
    base_url = _normalize_base_url(req.base_url)
    headers = _build_headers()

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        _activate_ppt_runtime(base_url)

    try:
        runner_map = {
            "local": _generate_local,
            "cloud_sync": _generate_cloud_sync,
            "cloud_async": _generate_cloud_async,
        }
        ordered_providers: List[str]
        if req.provider == "auto":
            # Presenton self-host commonly exposes `generate` and `generate/async`.
            ordered_providers = ["local", "cloud_async", "cloud_sync"]
        else:
            ordered_providers = [req.provider]

        errors: List[str] = []
        for provider in ordered_providers:
            runner = runner_map[provider]
            try:
                result = runner(base_url, headers, req)
                return _decorate_result_urls(result, base_url)
            except HTTPException as exc:
                errors.append(f"{provider}: {exc.detail}")
                if req.provider != "auto":
                    raise
                continue
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                if req.provider != "auto":
                    raise HTTPException(status_code=500, detail=str(exc)) from exc
                continue

        raise HTTPException(status_code=502, detail="; ".join(errors) if errors else "Presenton generation failed")
    finally:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(base_url)
                except HTTPException as exc:
                    logger.warning("Failed to restore default model runtime after sync generation: %s", exc.detail)


@router.post("/presenton/generate/async")
def submit_presenton_ppt_task(req: PresentonGenerateRequest):
    base_url = _normalize_base_url(req.base_url)
    headers = _build_headers()
    submit_url = f"{base_url}{CLOUD_ASYNC_PATH}"

    try:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            _activate_ppt_runtime(base_url)

        submit_data = _request_json("POST", submit_url, headers, _build_generation_payload(req))
        task_id = _extract_task_id(submit_data)
        if not task_id:
            raise HTTPException(status_code=502, detail="Presenton did not return task id")

        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            _ACTIVE_PPT_TASKS[task_id] = time.time()

        return {
            "success": True,
            "provider": "cloud_async",
            "status": "pending",
            "task_id": task_id,
            "message": submit_data.get("message") or "任务已提交",
            "raw": submit_data,
        }
    except Exception:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(base_url)
                except HTTPException as restore_exc:
                    logger.warning("Failed to restore default runtime after async submit failure: %s", restore_exc.detail)
        raise


@router.get("/presenton/generate/status/{task_id}")
def get_presenton_ppt_task_status(task_id: str, base_url: Optional[str] = None):
    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    status_data = _fetch_cloud_status(resolved_base_url, headers, task_id)
    status_value = str(status_data.get("status") or "pending").lower()
    message = str(status_data.get("message") or "")
    download_url, edit_url = _extract_urls(status_data, resolved_base_url)
    proxied_download = _build_download_proxy_url(download_url)
    proxied_edit = _build_presenton_proxy_url(edit_url, resolved_base_url)
    explicit_progress = _extract_progress_from_payload(status_data)

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        if status_value in TERMINAL_TASK_STATUSES:
            _ACTIVE_PPT_TASKS.pop(task_id, None)
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(resolved_base_url)
                except HTTPException as exc:
                    logger.warning("Failed to restore default runtime on task completion: %s", exc.detail)
        else:
            _ACTIVE_PPT_TASKS[task_id] = time.time()
            try:
                _activate_ppt_runtime(resolved_base_url)
            except HTTPException as exc:
                logger.warning("Failed to enforce qwen3 runtime during active task %s: %s", task_id, exc.detail)

    return {
        "success": True,
        "provider": "cloud_async",
        "task_id": task_id,
        "status": status_value,
        "message": message,
        "progress": explicit_progress if explicit_progress is not None else _estimate_progress(status_value, message),
        "download_url": proxied_download or download_url,
        "download_url_raw": download_url,
        "edit_url": proxied_edit or edit_url,
        "edit_url_raw": edit_url,
        "raw": status_data,
    }


@router.get("/presenton/download")
def proxy_presenton_download(
    target: str,
    base_url: Optional[str] = None,
):
    resolved_base_url = _normalize_base_url(base_url)
    decoded_target = unquote(str(target or "").strip())
    if not decoded_target:
        raise HTTPException(status_code=400, detail="Invalid download target")
    normalized_target = _join_url(resolved_base_url, decoded_target)
    if not normalized_target:
        raise HTTPException(status_code=400, detail="Invalid download target")
    if not _is_same_origin(normalized_target, resolved_base_url):
        raise HTTPException(status_code=400, detail="Download target origin is not allowed")

    headers: Dict[str, str] = {}
    if DEFAULT_PRESENTON_API_KEY:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"

    try:
        upstream = _PRESENTON_SESSION.get(normalized_target, headers=headers, timeout=max(REQUEST_TIMEOUT_SEC, 120))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Download proxy failed: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Presenton download failed ({upstream.status_code})")

    parsed = urlparse(normalized_target)
    filename = os.path.basename(parsed.path) or "presentation.pptx"
    content_type = upstream.headers.get(
        "content-type",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    headers_out = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=upstream.content, media_type=content_type, headers=headers_out)


@router.api_route("/presenton/proxy/{proxy_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_presenton_path(
    proxy_path: str,
    request: Request,
    base_url: Optional[str] = None,
):
    resolved_base_url = _normalize_base_url(base_url)
    normalized_path = f"/{(proxy_path or '').lstrip('/')}"
    upstream_url = f"{resolved_base_url}{normalized_path}"
    query = request.url.query
    if query:
        upstream_url = f"{upstream_url}?{query}"

    headers = _build_proxy_upstream_headers(request)
    body = await request.body()
    payload = body if body else None

    try:
        upstream = _PRESENTON_SESSION.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            data=payload,
            timeout=max(REQUEST_TIMEOUT_SEC, 120),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Presenton proxy failed: {exc}") from exc

    upstream_headers = _filter_proxy_response_headers(dict(upstream.headers), resolved_base_url)
    content_type = upstream.headers.get("content-type", "")
    content = upstream.content

    if any(token in content_type.lower() for token in PROXY_REWRITE_CONTENT_TYPES):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="ignore")
        rewritten = _rewrite_presenton_text_payload(text, resolved_base_url)
        content = rewritten.encode("utf-8")
        if content_type:
            base_mime = content_type.split(";")[0].strip()
            upstream_headers["Content-Type"] = f"{base_mime}; charset=utf-8"

    return Response(content=content, status_code=upstream.status_code, headers=upstream_headers)
