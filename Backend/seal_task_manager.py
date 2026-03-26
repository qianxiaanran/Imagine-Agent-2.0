from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from runtime_storage import RUNTIME_CACHE_ROOT, ensure_runtime_layout, migrate_legacy_runtime_files
from task_registry import build_task_result_link, get_task, upsert_task


ensure_runtime_layout()
migrate_legacy_runtime_files()

SEAL_TASK_RESULT_ROOT = Path(RUNTIME_CACHE_ROOT) / "seal_task_results"


def _ensure_seal_task_layout() -> None:
    SEAL_TASK_RESULT_ROOT.mkdir(parents=True, exist_ok=True)


def _result_path(task_id: str) -> Path:
    return SEAL_TASK_RESULT_ROOT / f"{str(task_id or '').strip()}.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def register_seal_task(
    *,
    filename: str,
    user_id: str,
    source_url: str,
    file_type: str,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ensure_seal_task_layout()
    task_id = str(uuid.uuid4())
    safe_filename = str(filename or "seal-source").strip() or "seal-source"
    return upsert_task(
        {
            "task_id": task_id,
            "task_type": "seal",
            "user_id": str(user_id or "anonymous").strip() or "anonymous",
            "title": f"印章提取 · {safe_filename}",
            "status": "running",
            "progress": 16,
            "error_message": None,
            "result_link": build_task_result_link(task_id),
            "retry_supported": False,
            "detail": {
                "filename": safe_filename,
                "file_url": source_url,
                "source_url": source_url,
                "file_type": str(file_type or "").strip(),
                "settings": settings or {},
            },
            "source_payload": {
                "filename": safe_filename,
                "source_url": source_url,
                "file_type": str(file_type or "").strip(),
                "settings": settings or {},
                "user_id": str(user_id or "anonymous").strip() or "anonymous",
            },
        }
    )


def complete_seal_task(task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_seal_task_layout()
    task = get_task(task_id) or {}
    normalized_result = result if isinstance(result, dict) else {"raw": str(result)}
    raw_result_path = _result_path(task_id)
    with raw_result_path.open("w", encoding="utf-8") as fp:
        json.dump(normalized_result, fp, ensure_ascii=False, indent=2)

    source_payload = dict(task.get("source_payload") or {})
    detail = dict(task.get("detail") or {})
    raw_items = normalized_result.get("items") if isinstance(normalized_result.get("items"), list) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    selected_index = _safe_int(normalized_result.get("selected_index") or 0, 0)
    if items:
        selected_index = max(0, min(selected_index, len(items) - 1))
        selected_item = items[selected_index]
    else:
        selected_index = 0
        selected_item = normalized_result

    download_url = str(selected_item.get("result_url") or normalized_result.get("result_url") or "").strip()
    archive_url = str(normalized_result.get("archive_url") or "").strip()
    item_count = len(items) or _safe_int(normalized_result.get("item_count") or (1 if download_url else 0), 0)
    status = "completed" if (download_url or archive_url or item_count > 0) else "failed"
    error_message = None if status == "completed" else "Seal extraction did not produce any downloadable result"

    detail.update(
        {
            "filename": normalized_result.get("source_name") or source_payload.get("filename") or detail.get("filename"),
            "file_url": normalized_result.get("source_url") or source_payload.get("source_url") or detail.get("file_url"),
            "source_url": normalized_result.get("source_url") or source_payload.get("source_url") or detail.get("source_url"),
            "file_type": source_payload.get("file_type") or detail.get("file_type"),
            "settings": source_payload.get("settings") or detail.get("settings") or {},
            "download_url": download_url,
            "download_name": selected_item.get("download_name") or normalized_result.get("download_name") or "",
            "archive_url": archive_url,
            "archive_download_name": normalized_result.get("archive_download_name") or "",
            "item_count": item_count,
            "selected_index": selected_index,
            "selected_label": selected_item.get("candidate_label") or "",
            "result_content_type": selected_item.get("content_type") or normalized_result.get("content_type") or "image/png",
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


def fail_seal_task(task_id: str, error_message: str) -> Dict[str, Any]:
    return upsert_task(
        {
            "task_id": task_id,
            "status": "failed",
            "progress": 100,
            "error_message": str(error_message or "Seal extraction failed"),
        }
    )


def get_seal_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
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
