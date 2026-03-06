from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from admin_utils import ROLE_ADMIN, require_role
from deepseek_llm import ask_llm

router = APIRouter(prefix="/api/presentation", tags=["Presentation"])

DEFAULT_PRESENTON_BASE_URL = os.getenv("PRESENTON_BASE_URL", "http://127.0.0.1:5000").strip()
DEFAULT_PRESENTON_API_KEY = os.getenv("PRESENTON_API_KEY", "").strip()

LOCAL_GENERATE_PATH = os.getenv("PRESENTON_LOCAL_PATH", "/api/v1/ppt/presentation/generate").strip()
CLOUD_SYNC_PATH = os.getenv("PRESENTON_SYNC_PATH", "/api/v1/ppt/presentation/generate/sync").strip()
CLOUD_ASYNC_PATH = os.getenv("PRESENTON_ASYNC_PATH", "/api/v1/ppt/presentation/generate/async").strip()
STATUS_PATH_TEMPLATE = os.getenv("PRESENTON_STATUS_PATH_TEMPLATE", "/api/v1/ppt/presentation/status/{task_id}").strip()
TEMPLATE_LIST_PATHS = [
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH", "/api/v1/ppt/template/all").strip() or "/api/v1/ppt/template/all",
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH_V3", "/api/v3/standard-template").strip() or "/api/v3/standard-template",
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH_TM", "/api/v1/ppt/template-management/summary").strip()
    or "/api/v1/ppt/template-management/summary",
]
TEMPLATE_DETAIL_PATHS = [
    os.getenv("PRESENTON_TEMPLATE_DETAIL_PATH", "/api/v1/ppt/template/{template_id}").strip() or "/api/v1/ppt/template/{template_id}",
    os.getenv("PRESENTON_TEMPLATE_DETAIL_PATH_V3", "/api/v3/standard-template/{template_id}").strip() or "/api/v3/standard-template/{template_id}",
]
TEMPLATE_REGISTRY_FILE = Path(
    os.getenv("PRESENTON_TEMPLATE_REGISTRY_FILE", str(Path(__file__).resolve().parent / "data" / "presentation_templates.json"))
)

REQUEST_TIMEOUT_SEC = float(os.getenv("PRESENTON_REQUEST_TIMEOUT_SEC", "180"))
POLL_TIMEOUT_SEC = float(os.getenv("PRESENTON_POLL_TIMEOUT_SEC", "900"))
POLL_INTERVAL_SEC = float(os.getenv("PRESENTON_POLL_INTERVAL_SEC", "2"))
INVALID_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
PRESENTON_PROXY_PREFIX = "/api/presentation/presenton/proxy"
PRESENTON_USER_CONFIG_PATH = os.getenv("PRESENTON_USER_CONFIG_PATH", "/api/user-config").strip() or "/api/user-config"
PPT_RUNTIME_MODEL = os.getenv("PRESENTON_PPT_RUNTIME_MODEL", "qwen3:1.7b").strip() or "qwen3:1.7b"
PPT_RESTORE_MODEL = os.getenv("PRESENTON_PPT_RESTORE_MODEL", "qwen2.5-coder:latest").strip() or "qwen2.5-coder:latest"
PPT_IMAGE_PROVIDER_DISABLED = os.getenv("PRESENTON_PPT_IMAGE_PROVIDER_DISABLED", "none").strip() or "none"
PPT_IMAGE_PROVIDER_RESTORE = os.getenv("PRESENTON_PPT_IMAGE_PROVIDER_RESTORE", "").strip()
PPT_FORCE_IMAGE_PROVIDER_OVERRIDE = os.getenv("PRESENTON_PPT_FORCE_IMAGE_PROVIDER_OVERRIDE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_MODEL_KEEP_ALIVE = os.getenv("PRESENTON_PPT_MODEL_KEEP_ALIVE", "1h").strip() or "1h"
OLLAMA_CONTROL_URL = (
    os.getenv("PRESENTON_OLLAMA_CONTROL_URL")
    or os.getenv("OLLAMA_API_BASE")
    or "http://127.0.0.1:11434"
).strip().rstrip("/")
OLLAMA_CONTROL_TIMEOUT_SEC = float(os.getenv("PRESENTON_OLLAMA_CONTROL_TIMEOUT_SEC", "8"))
PPT_RUNTIME_CONFIG_TIMEOUT_SEC = float(os.getenv("PRESENTON_RUNTIME_CONFIG_TIMEOUT_SEC", "20"))
PPT_RUNTIME_SWITCH_STRICT = os.getenv("PRESENTON_RUNTIME_SWITCH_STRICT", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_ENFORCE_SINGLE_OLLAMA_MODEL = os.getenv("PRESENTON_ENFORCE_SINGLE_OLLAMA_MODEL", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
_TEMPLATE_REGISTRY_LOCK = threading.Lock()
_LAST_IMAGE_PROVIDER: Optional[str] = None
logger = logging.getLogger(__name__)

BUILTIN_TEMPLATE_CATALOG: List[Dict[str, Any]] = [
    {"template_id": "general", "name": "general", "description": "通用商务模板", "source": "builtin"},
    {"template_id": "corporate", "name": "corporate", "description": "企业汇报模板", "source": "builtin"},
    {"template_id": "minimal", "name": "minimal", "description": "简洁极简模板", "source": "builtin"},
]


class PresentonGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=4, max_length=12000, description="PPT 生成提示词")
    n_slides: int = Field(default=10, ge=3, le=40, description="页数")
    language: str = Field(default="Chinese", max_length=64)
    template: str = Field(default="general", max_length=64)
    export_as: str = Field(default="pptx", max_length=16)
    tone: str = Field(default="professional", max_length=32)
    verbosity: str = Field(default="standard", max_length=32)
    image_type: Optional[str] = Field(default="none", max_length=32)
    content_generation: Optional[str] = Field(default=None, max_length=32)
    markdown_emphasis: Optional[str] = Field(default=None, max_length=32)
    web_search: Optional[bool] = None
    slides_markdown: Optional[List[str]] = None
    slides_layout: Optional[List[str]] = None
    provider: Literal["auto", "local", "cloud_sync", "cloud_async"] = "auto"
    base_url: Optional[str] = None


class PresentonOutlineRequest(BaseModel):
    input_mode: Literal["topic", "document", "longText"] = "topic"
    analysis_framework: str = Field(default="4P框架", max_length=64)
    analysis_input: str = Field(default="", max_length=14000)
    document_name: Optional[str] = Field(default=None, max_length=256)
    n_slides: int = Field(default=8, ge=3, le=40)
    language: str = Field(default="Chinese", max_length=64)
    require_metrics: bool = True
    include_images: bool = False
    model_backend: Literal["local", "cloud"] = "local"


class PresentonTemplateImportRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=120)
    alias: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=300)


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


def _runtime_config_timeout() -> float:
    upper = REQUEST_TIMEOUT_SEC if REQUEST_TIMEOUT_SEC > 0 else 20.0
    preferred = PPT_RUNTIME_CONFIG_TIMEOUT_SEC if PPT_RUNTIME_CONFIG_TIMEOUT_SEC > 0 else 20.0
    return max(3.0, min(upper, preferred))


def _handle_runtime_switch_error(step: str, exc: Exception) -> None:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    logger.warning("%s: %s", step, detail)
    if PPT_RUNTIME_SWITCH_STRICT:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=f"{step}: {detail}") from exc


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


def _set_presenton_ollama_model(base_url: str, model_name: str, image_provider: Optional[str] = None) -> None:
    runtime_timeout = _runtime_config_timeout()
    payload = {
        "LLM": "ollama",
        "OLLAMA_MODEL": model_name,
    }
    if image_provider is not None:
        payload["IMAGE_PROVIDER"] = str(image_provider).strip()
    try:
        _request_json(
            "POST",
            f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
            {"Content-Type": "application/json"},
            payload=payload,
            timeout=runtime_timeout,
        )
    except HTTPException as exc:
        # Some deployments may not accept IMAGE_PROVIDER in user config update payload.
        if image_provider is not None:
            logger.warning("Failed to set IMAGE_PROVIDER in user config, fallback to model-only update: %s", exc.detail)
            payload.pop("IMAGE_PROVIDER", None)
            _request_json(
                "POST",
                f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
                {"Content-Type": "application/json"},
                payload=payload,
                timeout=runtime_timeout,
            )
            return
        raise


def _read_presenton_user_config(base_url: str) -> Dict[str, Any]:
    try:
        data = _request_json(
            "GET",
            f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
            {"Content-Type": "application/json"},
            payload=None,
            timeout=_runtime_config_timeout(),
        )
    except HTTPException:
        return {}
    return data if isinstance(data, dict) else {}


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


def _enforce_single_ollama_model_if_needed(target_model: str, stage: str) -> None:
    if not PPT_ENFORCE_SINGLE_OLLAMA_MODEL:
        return
    try:
        _ensure_only_ollama_model(target_model)
    except Exception as exc:
        _handle_runtime_switch_error(f"Failed to enforce single Ollama model during {stage}", exc)


def _activate_ppt_runtime(base_url: str) -> None:
    global _LAST_IMAGE_PROVIDER
    if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE and _LAST_IMAGE_PROVIDER is None:
        try:
            current = _read_presenton_user_config(base_url)
            current_provider = str(current.get("IMAGE_PROVIDER") or "").strip()
            if current_provider:
                _LAST_IMAGE_PROVIDER = current_provider
        except Exception as exc:
            _handle_runtime_switch_error("Failed to read Presenton user config before runtime activation", exc)

    target_image_provider = PPT_IMAGE_PROVIDER_DISABLED if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE else None
    try:
        _set_presenton_ollama_model(base_url, PPT_RUNTIME_MODEL, image_provider=target_image_provider)
    except Exception as exc:
        _handle_runtime_switch_error("Failed to activate PPT runtime model", exc)
        return
    _enforce_single_ollama_model_if_needed(PPT_RUNTIME_MODEL, "runtime activation")


def _restore_default_runtime(base_url: str) -> None:
    restore_provider = None
    if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE:
        restore_provider = _LAST_IMAGE_PROVIDER or PPT_IMAGE_PROVIDER_RESTORE
    try:
        _set_presenton_ollama_model(base_url, PPT_RESTORE_MODEL, image_provider=restore_provider if restore_provider else None)
    except Exception as exc:
        _handle_runtime_switch_error("Failed to restore default runtime model", exc)
        return
    _enforce_single_ollama_model_if_needed(PPT_RESTORE_MODEL, "runtime restore")


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


def _extract_status_value(payload: Dict[str, Any]) -> str:
    direct = str(payload.get("status") or payload.get("state") or "").strip().lower()
    if direct:
        return direct
    data = payload.get("data")
    if isinstance(data, dict):
        nested = str(data.get("status") or data.get("state") or data.get("task_status") or "").strip().lower()
        if nested:
            return nested
    return "pending"


def _extract_status_message(payload: Dict[str, Any]) -> str:
    message = str(payload.get("message") or payload.get("detail") or payload.get("error_message") or "").strip()
    if message:
        return message
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        nested_error = str(
            error_payload.get("detail")
            or error_payload.get("message")
            or error_payload.get("error")
            or ""
        ).strip()
        if nested_error:
            return nested_error
    data = payload.get("data")
    if isinstance(data, dict):
        nested_message = str(data.get("message") or data.get("detail") or "").strip()
        if nested_message:
            return nested_message
    return ""


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


def _extract_markdown_json(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}

    fenced_match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidate = fenced_match.group(1).strip() if fenced_match else text

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    first = candidate.find("{")
    last = candidate.rfind("}")
    if first >= 0 and last > first:
        maybe_json = candidate[first:last + 1]
        try:
            parsed = json.loads(maybe_json)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _sanitize_outline_title(title: Optional[str], fallback: str) -> str:
    value = str(title or "").strip()
    return value[:120] if value else fallback


def _fallback_outline(req: PresentonOutlineRequest, input_text: str) -> Dict[str, Any]:
    topic = _sanitize_outline_title(input_text.splitlines()[0] if input_text else "", "业务汇报")
    slide_count = max(3, min(40, int(req.n_slides or 8)))
    section_titles = [
        "封面", "目录", "背景与目标", "现状与问题", "方案设计",
        "实施路径", "关键指标", "风险与对策", "总结与行动项",
    ]
    slides: List[Dict[str, Any]] = []
    for idx in range(slide_count):
        title = section_titles[idx] if idx < len(section_titles) else f"补充页 {idx + 1}"
        points = [
            f"围绕“{topic}”提炼本页核心结论。",
            "给出 2-3 条关键事实或数据依据。",
            "明确本页行动建议与预期结果。",
        ]
        slides.append(
            {
                "index": idx + 1,
                "title": title,
                "points": points,
                "notes": "可根据业务真实数据继续补充。",
            }
        )
    return {
        "title": f"{topic}汇报",
        "subtitle": f"{req.analysis_framework} · {req.language}",
        "slides": slides,
    }


def _normalize_outline_payload(payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback

    slides_raw = payload.get("slides")
    if not isinstance(slides_raw, list) or not slides_raw:
        return fallback

    normalized_slides: List[Dict[str, Any]] = []
    for idx, item in enumerate(slides_raw, start=1):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("heading") or f"第 {idx} 页").strip()
            points_raw = item.get("points") or item.get("bullets") or []
            notes = str(item.get("notes") or item.get("speaker_notes") or "").strip()
        else:
            title = f"第 {idx} 页"
            points_raw = []
            notes = ""

        points: List[str] = []
        if isinstance(points_raw, list):
            points = [str(point).strip() for point in points_raw if str(point).strip()]
        elif isinstance(points_raw, str):
            points = [line.strip("- \t") for line in points_raw.splitlines() if line.strip()]

        if not points:
            points = [
                "补充本页核心观点。",
                "补充关键支撑信息。",
            ]

        normalized_slides.append(
            {
                "index": idx,
                "title": title[:120],
                "points": points[:8],
                "notes": notes[:800],
            }
        )

    return {
        "title": _sanitize_outline_title(payload.get("title"), fallback.get("title", "演示文稿")),
        "subtitle": _sanitize_outline_title(payload.get("subtitle"), fallback.get("subtitle", "")),
        "slides": normalized_slides[:40],
    }


def _build_outline_prompt(req: PresentonOutlineRequest, input_text: str) -> str:
    metrics_req = "是" if req.require_metrics else "否"
    image_req = "开启" if req.include_images else "关闭"
    return (
        "你是一名资深 PPT 策划顾问。"
        "\n请严格输出 JSON，不要输出除 JSON 外的任何内容。"
        "\nJSON 结构："
        '\n{"title":"", "subtitle":"", "slides":[{"title":"","points":[""],"notes":""}]}\n'
        f"\n目标页数：{req.n_slides} 页"
        f"\n语言：{req.language}"
        f"\n分析框架：{req.analysis_framework}"
        f"\n输入模式：{req.input_mode}"
        f"\n是否强调指标：{metrics_req}"
        f"\n图片建议：{image_req}"
        "\n每页要求：标题 + 3-6 条可执行要点 + 一条讲解备注。"
        "\n目录结构建议涵盖：封面、目录、背景、问题、方案、执行、风险、总结。"
        f"\n业务输入：\n{input_text}"
    )


def _ensure_template_registry_file() -> None:
    if TEMPLATE_REGISTRY_FILE.exists():
        return
    TEMPLATE_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_REGISTRY_FILE.write_text("[]", encoding="utf-8")


def _load_template_registry() -> List[Dict[str, Any]]:
    _ensure_template_registry_file()
    with _TEMPLATE_REGISTRY_LOCK:
        try:
            data = json.loads(TEMPLATE_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = []
    return data if isinstance(data, list) else []


def _save_template_registry(entries: List[Dict[str, Any]]) -> None:
    _ensure_template_registry_file()
    safe_entries = entries if isinstance(entries, list) else []
    with _TEMPLATE_REGISTRY_LOCK:
        TEMPLATE_REGISTRY_FILE.write_text(
            json.dumps(safe_entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_template_item(item: Dict[str, Any]) -> Dict[str, Any]:
    template_id = str(item.get("template_id") or item.get("id") or item.get("presentation_id") or "").strip()
    if not template_id:
        return {}
    return {
        "template_id": template_id,
        "name": str(item.get("name") or item.get("template_name") or template_id).strip()[:120],
        "description": str(item.get("description") or item.get("summary") or "").strip()[:300],
        "thumbnail_url": str(item.get("thumbnail_url") or item.get("thumbnail") or item.get("cover_url") or "").strip(),
        "source": str(item.get("source") or "presenton").strip(),
        "created_at": str(item.get("created_at") or "").strip(),
        "updated_at": str(item.get("updated_at") or "").strip(),
    }


def _extract_template_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    candidates: List[Any] = []
    for key in ("data", "templates", "items", "list", "result", "presentations"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates = value
            break
        if isinstance(value, dict):
            nested_list = value.get("items") or value.get("list")
            if isinstance(nested_list, list):
                candidates = nested_list
                break

    if not candidates and isinstance(payload.get("id"), (str, int)):
        candidates = [payload]

    normalized: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        normalized_item: Dict[str, Any] = {}
        template_field = item.get("template")
        if isinstance(template_field, dict):
            template_payload = dict(template_field)
            template_payload.setdefault(
                "template_id",
                template_payload.get("template_id") or template_payload.get("id") or item.get("presentation_id"),
            )
            if not template_payload.get("description") and item.get("layout_count") is not None:
                template_payload["description"] = f"Custom template · {item.get('layout_count')} layouts"
            template_payload.setdefault("source", "presenton_custom")
            normalized_item = _normalize_template_item(template_payload)

        if not normalized_item:
            normalized_item = _normalize_template_item(item)

        if not normalized_item and item.get("presentation_id"):
            normalized_item = _normalize_template_item(
                {
                    "template_id": item.get("presentation_id"),
                    "name": item.get("name") or item.get("presentation_id"),
                    "description": f"Custom template · {item.get('layout_count', 0)} layouts",
                    "source": "presenton_custom",
                    "updated_at": item.get("last_updated_at") or item.get("updated_at") or "",
                }
            )
        if normalized_item:
            normalized.append(normalized_item)
    return normalized


def _fetch_template_list_from_presenton(base_url: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    errors: List[str] = []
    merged: Dict[str, Dict[str, Any]] = {}
    for path in TEMPLATE_LIST_PATHS:
        try:
            payload = _request_json("GET", f"{base_url}{path}", headers, payload=None, timeout=max(REQUEST_TIMEOUT_SEC, 20))
            items = _extract_template_items(payload)
            for item in items:
                template_id = str(item.get("template_id") or "").strip()
                if not template_id:
                    continue
                previous = merged.get(template_id, {})
                merged[template_id] = {
                    "template_id": template_id,
                    "name": str(item.get("name") or previous.get("name") or template_id),
                    "description": str(item.get("description") or previous.get("description") or ""),
                    "thumbnail_url": str(item.get("thumbnail_url") or previous.get("thumbnail_url") or ""),
                    "source": str(item.get("source") or previous.get("source") or "presenton"),
                    "created_at": str(item.get("created_at") or previous.get("created_at") or ""),
                    "updated_at": str(item.get("updated_at") or previous.get("updated_at") or ""),
                }
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue
    if merged:
        return list(merged.values())
    if errors:
        logger.warning("Template list fetch failed: %s", " | ".join(errors))
    return []


def _fetch_template_detail_from_presenton(base_url: str, headers: Dict[str, str], template_id: str) -> Dict[str, Any]:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    errors: List[str] = []
    for path in TEMPLATE_DETAIL_PATHS:
        resolved = path.replace("{template_id}", requests.utils.quote(clean_id, safe=""))
        try:
            payload = _request_json("GET", f"{base_url}{resolved}", headers, payload=None, timeout=max(REQUEST_TIMEOUT_SEC, 20))
            items = _extract_template_items(payload)
            if items:
                return items[0]
            if isinstance(payload, dict):
                normalized = _normalize_template_item(payload)
                if normalized:
                    return normalized
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue

    # v1 may not expose detail endpoint for built-in templates; fallback to list scan.
    template_list = _fetch_template_list_from_presenton(base_url, headers)
    for item in template_list:
        if str(item.get("template_id")) == clean_id:
            return item

    detail = errors[-1] if errors else "Template not found"
    raise HTTPException(status_code=404, detail=detail)


def _build_generation_payload(req: PresentonGenerateRequest) -> Dict[str, Any]:
    resolved_image_type = str(req.image_type or "none").strip().lower()
    if resolved_image_type in {"", "off", "false", "disabled", "0", "no"}:
        resolved_image_type = "none"

    no_image_constraint = (
        "硬性约束：默认关闭并禁止配图。不要生成或请求任何图片/插画/照片，"
        "不要触发图片素材检索，页面内容仅使用文字、图表和形状布局。"
    )
    prompt_text = str(req.prompt or "").strip()
    if resolved_image_type == "none":
        prompt_text = f"{prompt_text}\n{no_image_constraint}".strip()

    payload: Dict[str, Any] = {
        "prompt": prompt_text,
        "content": prompt_text,
        "instructions": prompt_text,
        "n_slides": req.n_slides,
        "language": req.language,
        "template": req.template,
        "export_as": req.export_as,
        "tone": req.tone,
        "verbosity": req.verbosity,
        "image_type": resolved_image_type,
    }

    if resolved_image_type == "none":
        payload["web_search"] = False
        payload["include_images"] = False
        payload["enable_images"] = False
        payload["disable_image_generation"] = True
        payload["image_provider"] = "none"

    if req.content_generation:
        payload["content_generation"] = req.content_generation
    if req.markdown_emphasis:
        payload["markdown_emphasis"] = req.markdown_emphasis
    if req.web_search is not None and resolved_image_type != "none":
        payload["web_search"] = bool(req.web_search)
    if isinstance(req.slides_markdown, list) and req.slides_markdown:
        payload["slides_markdown"] = req.slides_markdown
    if isinstance(req.slides_layout, list) and req.slides_layout:
        payload["slides_layout"] = req.slides_layout
    return payload


def _request_generation_with_no_image_fallback(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float = REQUEST_TIMEOUT_SEC,
) -> Dict[str, Any]:
    def _template_retry_candidates(raw_template: Any) -> List[str]:
        value = str(raw_template or "").strip()
        if not value:
            return ["general"]
        candidates: List[str] = [value]
        lowered = value.lower()
        if lowered in {"auto", "default"}:
            candidates.append("general")
        if lowered.startswith("custom-") and len(value) > len("custom-"):
            candidates.append(value[len("custom-"):])
        if lowered.startswith("neo-") and len(value) > len("neo-"):
            candidates.append(value[len("neo-"):])
        unique: List[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        return unique or ["general"]

    template_candidates = _template_retry_candidates(payload.get("template"))
    collected_errors: List[str] = []

    for idx, candidate in enumerate(template_candidates):
        candidate_payload = dict(payload)
        candidate_payload["template"] = candidate
        try:
            data = _request_json(method, url, headers, candidate_payload, timeout=timeout)
            original_template = str(payload.get("template") or "").strip()
            if original_template and candidate != original_template:
                logger.warning("Template fallback applied: requested=%s, used=%s", original_template, candidate)
            return data
        except HTTPException as exc:
            detail_text = str(exc.detail or "")
            detail_l = detail_text.lower()

            if str(candidate_payload.get("image_type") or "").lower() == "none" and any(
                token in detail_l for token in ("image_type", "validation", "extra", "unprocessable")
            ):
                fallback_payload = dict(candidate_payload)
                # Keep hard no-image intent and only trim extra compatibility fields.
                for key in ("include_images", "enable_images", "disable_image_generation", "image_provider"):
                    fallback_payload.pop(key, None)
                fallback_payload["image_type"] = "none"
                fallback_payload["web_search"] = False
                logger.warning(
                    "Retrying generation with minimal no-image fields due upstream validation: %s",
                    exc.detail,
                )
                try:
                    return _request_json(method, url, headers, fallback_payload, timeout=timeout)
                except HTTPException as fallback_exc:
                    detail_text = str(fallback_exc.detail or detail_text)
                    detail_l = detail_text.lower()
                    if any(token in detail_l for token in ("image_type", "image provider", "image_provider")):
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                "Presenton does not accept no-image control fields in current endpoint; "
                                "request is blocked to prevent unexpected auto image generation. "
                                f"Upstream detail: {detail_text}"
                            ),
                        ) from fallback_exc
                    collected_errors.append(f"{candidate}: {detail_text}")
                    if not any(token in detail_l for token in ("template not found", "invalid template", "unknown template")):
                        raise fallback_exc
                    if idx < len(template_candidates) - 1:
                        continue
                    raise fallback_exc

            collected_errors.append(f"{candidate}: {detail_text}")
            if not any(token in detail_l for token in ("template not found", "invalid template", "unknown template")):
                raise
            if idx < len(template_candidates) - 1:
                logger.warning("Template %s rejected, retrying next candidate", candidate)
                continue
            raise

    raise HTTPException(status_code=502, detail="; ".join(collected_errors) if collected_errors else "Generation failed")


def _generate_local(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    url = f"{base_url}{LOCAL_GENERATE_PATH}"
    data = _request_generation_with_no_image_fallback("POST", url, headers, payload)
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
    data = _request_generation_with_no_image_fallback(
        "POST",
        url,
        headers,
        payload,
        timeout=max(REQUEST_TIMEOUT_SEC, POLL_TIMEOUT_SEC),
    )
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
    submit_data = _request_generation_with_no_image_fallback("POST", submit_url, headers, payload)
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


@router.post("/presenton/outline/generate")
def generate_presenton_outline(req: PresentonOutlineRequest):
    slide_count = max(3, min(40, int(req.n_slides or 8)))
    raw_input = str(req.analysis_input or "").strip()
    doc_name = str(req.document_name or "").strip()

    if req.input_mode == "topic" and not raw_input:
        raise HTTPException(status_code=400, detail="请先输入 PPT 主题")
    if req.input_mode == "document" and not raw_input and not doc_name:
        raise HTTPException(status_code=400, detail="请先上传文档或补充文档说明")
    if req.input_mode == "longText" and not raw_input:
        raise HTTPException(status_code=400, detail="请先输入或粘贴正文内容")

    input_parts: List[str] = []
    if doc_name:
        input_parts.append(f"文档名称：{doc_name}")
    if raw_input:
        input_parts.append(raw_input)
    if not input_parts:
        input_parts.append("请围绕进出口企业协同办公主题生成完整汇报大纲。")
    input_text = "\n".join(input_parts)

    fallback_outline = _fallback_outline(req, input_text)
    prompt = _build_outline_prompt(req, input_text)
    llm_raw = ask_llm(prompt, model_type=req.model_backend)
    parsed = _extract_markdown_json(llm_raw)
    outline = _normalize_outline_payload(parsed, fallback_outline)

    return {
        "success": True,
        "outline": {
            "title": outline["title"],
            "subtitle": outline.get("subtitle") or f"{req.analysis_framework} · {req.language}",
            "slides": outline["slides"][:slide_count],
            "language": req.language,
            "analysis_framework": req.analysis_framework,
        },
        "raw_model_output": llm_raw[:6000] if llm_raw else "",
    }


@router.get("/presenton/template/catalog")
def get_presenton_template_catalog(base_url: Optional[str] = None):
    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    remote_items = _fetch_template_list_from_presenton(resolved_base_url, headers)
    imported_items = _load_template_registry()

    merged: Dict[str, Dict[str, Any]] = {}
    for source_items in (BUILTIN_TEMPLATE_CATALOG, remote_items, imported_items):
        for raw_item in source_items:
            item = _normalize_template_item(raw_item) if not raw_item.get("template_id") else raw_item
            template_id = str(item.get("template_id") or "").strip()
            if not template_id:
                continue
            prev = merged.get(template_id, {})
            merged[template_id] = {
                "template_id": template_id,
                "name": str(item.get("name") or prev.get("name") or template_id),
                "description": str(item.get("description") or prev.get("description") or ""),
                "thumbnail_url": str(item.get("thumbnail_url") or prev.get("thumbnail_url") or ""),
                "source": str(item.get("source") or prev.get("source") or "presenton"),
                "created_at": str(item.get("created_at") or prev.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or prev.get("updated_at") or ""),
                "imported": bool(item.get("imported") or prev.get("imported") or False),
            }

    data = list(merged.values())
    data.sort(key=lambda item: (0 if item.get("imported") else 1, str(item.get("name") or "").lower()))
    return {"success": True, "data": data}


@router.get("/presenton/template/imported")
def list_imported_presenton_templates(
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    _ = ctx
    return {"success": True, "data": _load_template_registry()}


@router.post("/presenton/template/import")
def import_presenton_template(
    payload: PresentonTemplateImportRequest,
    base_url: Optional[str] = None,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    template_id = str(payload.template_id or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    detail = _fetch_template_detail_from_presenton(resolved_base_url, headers, template_id)
    now = datetime.now(timezone.utc).isoformat()
    imported = {
        "template_id": template_id,
        "name": str(payload.alias or detail.get("name") or template_id).strip()[:120],
        "description": str(payload.description or detail.get("description") or "").strip()[:300],
        "thumbnail_url": str(detail.get("thumbnail_url") or "").strip(),
        "source": "presenton_import",
        "imported": True,
        "created_at": now,
        "updated_at": now,
    }

    entries = _load_template_registry()
    updated_entries: List[Dict[str, Any]] = []
    replaced = False
    for item in entries:
        if str(item.get("template_id") or "").strip() == template_id:
            merged_item = dict(item)
            merged_item.update(imported)
            merged_item["created_at"] = item.get("created_at") or now
            updated_entries.append(merged_item)
            replaced = True
        else:
            updated_entries.append(item)
    if not replaced:
        updated_entries.append(imported)

    _save_template_registry(updated_entries)
    logger.info("Admin %s imported template %s", ctx.get("user_id"), template_id)
    return {"success": True, "data": imported}


@router.delete("/presenton/template/import/{template_id}")
def delete_imported_presenton_template(
    template_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    clean_id = str(template_id or "").strip()
    entries = _load_template_registry()
    remained = [item for item in entries if str(item.get("template_id") or "").strip() != clean_id]
    if len(remained) == len(entries):
        raise HTTPException(status_code=404, detail="Template not found in imported list")
    _save_template_registry(remained)
    logger.info("Admin %s removed imported template %s", ctx.get("user_id"), clean_id)
    return {"success": True}


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

        submit_data = _request_generation_with_no_image_fallback(
            "POST",
            submit_url,
            headers,
            _build_generation_payload(req),
        )
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
    status_value = _extract_status_value(status_data)
    message = _extract_status_message(status_data)
    download_url, edit_url = _extract_urls(status_data, resolved_base_url)
    proxied_download = _build_download_proxy_url(download_url)
    proxied_edit = _build_presenton_proxy_url(edit_url, resolved_base_url)
    explicit_progress = _extract_progress_from_payload(status_data)

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        if status_value in TERMINAL_TASK_STATUSES:
            _ACTIVE_PPT_TASKS.pop(task_id, None)
            if status_value in {"failed", "error", "cancelled", "canceled"}:
                logger.warning(
                    "Presenton task %s finished with status=%s message=%s raw_error=%s",
                    task_id,
                    status_value,
                    message,
                    status_data.get("error"),
                )
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(resolved_base_url)
                except HTTPException as exc:
                    logger.warning("Failed to restore default runtime on task completion: %s", exc.detail)
        else:
            # Do not mutate runtime during polling; toggling global config mid-task can break Presenton jobs.
            _ACTIVE_PPT_TASKS[task_id] = time.time()

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
