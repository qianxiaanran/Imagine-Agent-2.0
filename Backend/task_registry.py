from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from runtime_storage import RUNTIME_CACHE_ROOT, ensure_runtime_layout, migrate_legacy_runtime_files


ensure_runtime_layout()
migrate_legacy_runtime_files()

TASK_REGISTRY_ROOT = Path(RUNTIME_CACHE_ROOT) / "task_center"
TASK_RECORDS_ROOT = TASK_REGISTRY_ROOT / "records"

_REGISTRY_LOCK = threading.Lock()

TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
STATUS_ALIAS_MAP = {
    "pending": "queued",
    "queued": "queued",
    "created": "queued",
    "submitted": "queued",
    "running": "running",
    "processing": "running",
    "in_progress": "running",
    "active": "running",
    "working": "running",
    "completed": "completed",
    "done": "completed",
    "success": "completed",
    "succeeded": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def _ensure_registry_layout() -> None:
    TASK_RECORDS_ROOT.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_file_path(task_id: str) -> Path:
    clean_id = str(task_id or "").strip()
    return TASK_RECORDS_ROOT / f"{clean_id}.json"


def _safe_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _safe_json_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    return str(value)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(_safe_json_value(payload), fp, ensure_ascii=False, indent=2)


def build_task_result_link(task_id: str) -> str:
    return f"/tasks?task={quote(str(task_id or '').strip())}"


def normalize_task_status(status: Any) -> str:
    value = str(status or "").strip().lower()
    if not value:
        return "queued"
    return STATUS_ALIAS_MAP.get(value, value)


def coerce_progress(progress: Any, status: Any = None) -> int:
    normalized_status = normalize_task_status(status)
    try:
        numeric = int(float(progress if progress is not None else 0))
    except Exception:
        numeric = 0
    numeric = max(0, min(100, numeric))
    if normalized_status == "completed":
        return 100
    if normalized_status == "failed":
        return max(1, numeric)
    if normalized_status == "cancelled":
        return 100
    return numeric


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    _ensure_registry_layout()
    clean_id = str(task_id or "").strip()
    if not clean_id:
        return None
    with _REGISTRY_LOCK:
        payload = _read_json(_task_file_path(clean_id))
    if not payload:
        return None
    payload["status"] = normalize_task_status(payload.get("status"))
    payload["progress"] = coerce_progress(payload.get("progress"), payload.get("status"))
    return payload


def upsert_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_registry_layout()
    task_id = str((payload or {}).get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")

    now_iso = _utc_now_iso()
    with _REGISTRY_LOCK:
        current = _read_json(_task_file_path(task_id)) or {}
        merged = dict(current)
        merged.update(_safe_json_value(payload))
        merged["task_id"] = task_id
        merged["task_type"] = str(merged.get("task_type") or current.get("task_type") or "").strip()
        merged["user_id"] = str(merged.get("user_id") or current.get("user_id") or "").strip()
        merged["status"] = normalize_task_status(merged.get("status") or current.get("status"))
        merged["progress"] = coerce_progress(merged.get("progress"), merged["status"])
        merged["started_at"] = str(
            merged.get("started_at")
            or current.get("started_at")
            or merged.get("created_at")
            or current.get("created_at")
            or now_iso
        )
        merged["updated_at"] = str(merged.get("updated_at") or now_iso)
        merged["title"] = str(
            merged.get("title")
            or current.get("title")
            or f"{merged['task_type'] or 'task'} task"
        ).strip()
        merged["error_message"] = (
            None if merged.get("error_message") in ("", None) else str(merged.get("error_message"))
        )
        merged["result_link"] = str(
            merged.get("result_link") or current.get("result_link") or build_task_result_link(task_id)
        ).strip()
        merged["retry_supported"] = bool(merged.get("retry_supported"))
        _write_json(_task_file_path(task_id), merged)
    return merged


def list_tasks(
    *,
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _ensure_registry_layout()
    normalized_user_id = str(user_id or "").strip()
    normalized_type = str(task_type or "").strip().lower()
    normalized_status = normalize_task_status(status) if status else ""

    rows: List[Dict[str, Any]] = []
    with _REGISTRY_LOCK:
        paths = list(TASK_RECORDS_ROOT.glob("*.json"))
        for path in paths:
            payload = _read_json(path)
            if not isinstance(payload, dict):
                continue
            payload["status"] = normalize_task_status(payload.get("status"))
            payload["progress"] = coerce_progress(payload.get("progress"), payload.get("status"))
            if normalized_user_id and str(payload.get("user_id") or "").strip() != normalized_user_id:
                continue
            if normalized_type and str(payload.get("task_type") or "").strip().lower() != normalized_type:
                continue
            if normalized_status and payload["status"] != normalized_status:
                continue
            rows.append(payload)

    rows.sort(
        key=lambda item: (
            str(item.get("updated_at") or item.get("started_at") or ""),
            str(item.get("task_id") or ""),
        ),
        reverse=True,
    )
    if offset > 0:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]
    return rows

