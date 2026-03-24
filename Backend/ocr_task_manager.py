from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from runtime_storage import RUNTIME_CACHE_ROOT, ensure_runtime_layout, migrate_legacy_runtime_files
from task_registry import build_task_result_link, get_task, upsert_task


ensure_runtime_layout()
migrate_legacy_runtime_files()

OCR_TASK_INPUT_ROOT = Path(RUNTIME_CACHE_ROOT) / "ocr_task_inputs"
OCR_TASK_RESULT_ROOT = Path(RUNTIME_CACHE_ROOT) / "ocr_task_results"

_OCR_RUNNER: Optional[Callable[[bytes, str, str], Dict[str, Any]]] = None


def _ensure_ocr_task_layout() -> None:
    OCR_TASK_INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OCR_TASK_RESULT_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    raw = str(filename or "").strip() or "ocr-document"
    clean = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in raw)
    return clean[:180] or "ocr-document"


def _input_path(task_id: str, filename: str) -> Path:
    return OCR_TASK_INPUT_ROOT / f"{task_id}_{_safe_filename(filename)}"


def _result_path(task_id: str) -> Path:
    return OCR_TASK_RESULT_ROOT / f"{task_id}.json"


def set_ocr_task_runner(runner: Optional[Callable[[bytes, str, str], Dict[str, Any]]]) -> None:
    global _OCR_RUNNER
    _OCR_RUNNER = runner


def register_ocr_task(
    *,
    file_bytes: bytes,
    filename: str,
    user_id: str,
    engine: str,
    file_url: str,
    file_type: str,
) -> Dict[str, Any]:
    _ensure_ocr_task_layout()
    task_id = str(uuid.uuid4())
    input_path = _input_path(task_id, filename)
    with input_path.open("wb") as fp:
        fp.write(file_bytes)

    return upsert_task(
        {
            "task_id": task_id,
            "task_type": "ocr",
            "user_id": str(user_id or "anonymous").strip() or "anonymous",
            "title": f"OCR 识别 · {filename}",
            "status": "running",
            "progress": 12,
            "started_at": None,
            "error_message": None,
            "result_link": build_task_result_link(task_id),
            "retry_supported": True,
            "detail": {
                "filename": filename,
                "engine": engine,
                "file_url": file_url,
                "file_type": file_type,
                "input_path": str(input_path),
            },
            "source_payload": {
                "input_path": str(input_path),
                "filename": filename,
                "engine": engine,
                "file_url": file_url,
                "file_type": file_type,
                "user_id": str(user_id or "anonymous").strip() or "anonymous",
            },
        }
    )


def complete_ocr_task(task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_ocr_task_layout()
    task = get_task(task_id) or {}
    normalized_result = result if isinstance(result, dict) else {"raw": str(result)}
    raw_result_path = _result_path(task_id)
    with raw_result_path.open("w", encoding="utf-8") as fp:
        json.dump(normalized_result, fp, ensure_ascii=False, indent=2)

    text_value = str(normalized_result.get("text") or "")
    has_explicit_error = bool(normalized_result.get("error"))
    text_is_error = text_value.startswith("❌") or text_value.startswith("[ERROR]")
    status = "failed" if has_explicit_error or text_is_error else "completed"
    error_message = normalized_result.get("error") or (text_value if text_is_error else None)
    source_payload = dict(task.get("source_payload") or {})
    detail = dict(task.get("detail") or {})
    detail.update(
        {
            "filename": source_payload.get("filename") or detail.get("filename"),
            "engine": source_payload.get("engine") or detail.get("engine"),
            "file_url": source_payload.get("file_url") or detail.get("file_url"),
            "file_type": source_payload.get("file_type") or detail.get("file_type"),
            "text_preview": text_value[:600],
            "text_length": len(text_value),
            "raw_result_path": str(raw_result_path),
        }
    )
    return upsert_task(
        {
            "task_id": task_id,
            "status": status,
            "progress": 100,
            "error_message": error_message,
            "detail": detail,
        }
    )


def fail_ocr_task(task_id: str, error_message: str) -> Dict[str, Any]:
    return upsert_task(
        {
            "task_id": task_id,
            "status": "failed",
            "progress": 100,
            "error_message": str(error_message or "OCR task failed"),
        }
    )


def get_ocr_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
    task = get_task(task_id)
    if not task:
        return None
    detail = dict(task.get("detail") or {})
    raw_result_path = str(detail.get("raw_result_path") or "").strip()
    if raw_result_path:
        path = Path(raw_result_path)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fp:
                    detail["raw_result"] = json.load(fp)
            except Exception:
                pass
    task["detail"] = detail
    return task


def _run_ocr_task(task_id: str, source_payload: Dict[str, Any]) -> None:
    if _OCR_RUNNER is None:
        fail_ocr_task(task_id, "OCR runner unavailable")
        return

    input_path = Path(str(source_payload.get("input_path") or "").strip())
    if not input_path.exists():
        fail_ocr_task(task_id, f"File not found: {input_path}")
        return

    try:
        with input_path.open("rb") as fp:
            file_bytes = fp.read()
        filename = str(source_payload.get("filename") or input_path.name)
        engine = str(source_payload.get("engine") or "standard")
        upsert_task({"task_id": task_id, "status": "running", "progress": 24, "error_message": None})
        result = _OCR_RUNNER(file_bytes, filename, engine)
        complete_ocr_task(task_id, result)
    except Exception as exc:
        fail_ocr_task(task_id, str(exc))


def retry_ocr_task(task_id: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    task = get_task(task_id)
    if not task:
        return False, "Task not found", None
    source_payload = dict(task.get("source_payload") or {})
    input_path = Path(str(source_payload.get("input_path") or "").strip())
    if not input_path.exists():
        return False, f"File not found: {input_path}", None
    if _OCR_RUNNER is None:
        return False, "OCR runner unavailable", None

    new_task_id = str(uuid.uuid4())
    new_task = upsert_task(
        {
            "task_id": new_task_id,
            "task_type": "ocr",
            "user_id": task.get("user_id"),
            "title": task.get("title") or f"OCR 识别 · {source_payload.get('filename') or input_path.name}",
            "status": "queued",
            "progress": 0,
            "error_message": None,
            "result_link": build_task_result_link(new_task_id),
            "retry_supported": True,
            "detail": {
                "filename": source_payload.get("filename") or input_path.name,
                "engine": source_payload.get("engine") or "standard",
                "file_url": source_payload.get("file_url"),
                "file_type": source_payload.get("file_type"),
                "input_path": str(input_path),
            },
            "source_payload": {
                **source_payload,
                "input_path": str(input_path),
                "filename": source_payload.get("filename") or input_path.name,
            },
        }
    )

    worker = threading.Thread(
        target=_run_ocr_task,
        args=(new_task_id, dict(new_task.get("source_payload") or {})),
        daemon=True,
        name=f"ocr-retry-{new_task_id[:8]}",
    )
    worker.start()
    return True, None, new_task

