from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from admin_utils import require_active_user
from audit_pipeline import get_job_snapshot, list_local_audit_jobs, retry_audit_job_with_result
from ocr_task_manager import get_ocr_task_detail, retry_ocr_task
from presentation_router import refresh_presenton_task_record, retry_presenton_task
from task_registry import build_task_result_link, get_task, list_tasks, normalize_task_status
from voice_files_processing import retry_voice_task


router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


def _task_type_label(task_type: str) -> str:
    mapping = {
        "audit": "审单任务",
        "ocr": "OCR 任务",
        "voice": "语音转写",
        "ppt": "PPT 生成",
    }
    return mapping.get(str(task_type or "").strip().lower(), "任务")


def _task_status_label(status: str) -> str:
    mapping = {
        "queued": "已排队",
        "running": "运行中",
        "completed": "已完成",
        "failed": "失败",
        "cancelled": "已取消",
    }
    return mapping.get(str(status or "").strip().lower(), status or "未知")


def _compact_task(task: Dict[str, Any]) -> Dict[str, Any]:
    detail = dict(task.get("detail") or {})
    return {
        "task_id": str(task.get("task_id") or "").strip(),
        "task_type": str(task.get("task_type") or "").strip().lower(),
        "task_type_label": _task_type_label(task.get("task_type")),
        "title": str(task.get("title") or _task_type_label(task.get("task_type"))).strip(),
        "status": normalize_task_status(task.get("status")),
        "status_label": _task_status_label(task.get("status")),
        "progress": int(task.get("progress") or 0),
        "started_at": task.get("started_at"),
        "updated_at": task.get("updated_at"),
        "error_message": task.get("error_message"),
        "result_link": task.get("result_link") or build_task_result_link(task.get("task_id")),
        "retry_supported": bool(task.get("retry_supported")),
        "summary": {
            "filename": detail.get("filename"),
            "template": detail.get("template"),
            "case_id": detail.get("case_id"),
            "doc_type": detail.get("doc_type"),
            "provider": detail.get("provider"),
            "download_url": detail.get("download_url"),
        },
    }


def _map_audit_task(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    detail = {
        "filename": snapshot.get("file_name"),
        "doc_type": snapshot.get("doc_type"),
        "case_id": snapshot.get("case_id"),
        "stage": snapshot.get("stage"),
        "workflow_state": snapshot.get("workflow_state"),
        "file_url": snapshot.get("file_url"),
        "case_documents": snapshot.get("case_documents"),
        "result": snapshot.get("result"),
    }
    doc_type = str(snapshot.get("doc_type") or "auto").strip()
    file_name = str(snapshot.get("file_name") or "document").strip()
    status = normalize_task_status(snapshot.get("status") or snapshot.get("stage"))
    return {
        "task_id": str(snapshot.get("job_id") or "").strip(),
        "task_type": "audit",
        "user_id": str(snapshot.get("user_id") or "").strip(),
        "title": f"审单 · {doc_type} · {file_name}",
        "status": status,
        "progress": int(snapshot.get("progress") or 0),
        "started_at": snapshot.get("created_at"),
        "updated_at": snapshot.get("updated_at"),
        "error_message": snapshot.get("error_message"),
        "result_link": build_task_result_link(snapshot.get("job_id")),
        "retry_supported": True,
        "detail": detail,
    }


def _merge_all_tasks(user_id: str) -> List[Dict[str, Any]]:
    registry_rows = list_tasks(user_id=user_id, limit=400, offset=0)
    for row in registry_rows[:16]:
        if str(row.get("task_type") or "").strip().lower() == "ppt" and normalize_task_status(row.get("status")) in {
            "queued",
            "running",
        }:
            try:
                refreshed = refresh_presenton_task_record(str(row.get("task_id") or "").strip())
            except Exception:
                refreshed = None
            if refreshed:
                row.update(refreshed)

    audit_rows: List[Dict[str, Any]] = []
    for job in list_local_audit_jobs(limit=400, offset=0):
        if str(job.get("user_id") or "").strip() != user_id:
            continue
        audit_rows.append(_map_audit_task(job))

    merged: Dict[str, Dict[str, Any]] = {}
    for row in audit_rows + registry_rows:
        task_id = str(row.get("task_id") or row.get("job_id") or "").strip()
        if not task_id:
            continue
        candidate = dict(row)
        if "job_id" in candidate and "task_id" not in candidate:
            candidate = _map_audit_task(candidate)
        existing = merged.get(task_id)
        if not existing:
            merged[task_id] = candidate
            continue
        existing_updated = str(existing.get("updated_at") or existing.get("started_at") or "")
        candidate_updated = str(candidate.get("updated_at") or candidate.get("started_at") or "")
        if candidate_updated >= existing_updated:
            merged[task_id] = candidate

    rows = list(merged.values())
    rows.sort(
        key=lambda item: (
            str(item.get("updated_at") or item.get("started_at") or ""),
            str(item.get("task_id") or ""),
        ),
        reverse=True,
    )
    return rows


def _filter_rows(
    rows: List[Dict[str, Any]],
    *,
    status: Optional[str],
    task_type: Optional[str],
) -> List[Dict[str, Any]]:
    normalized_status = normalize_task_status(status) if status else ""
    normalized_type = str(task_type or "").strip().lower()
    filtered = rows
    if normalized_status:
        if normalized_status == "running":
            filtered = [
                row
                for row in filtered
                if normalize_task_status(row.get("status")) in {"queued", "running"}
            ]
        else:
            filtered = [row for row in filtered if normalize_task_status(row.get("status")) == normalized_status]
    if normalized_type:
        filtered = [row for row in filtered if str(row.get("task_type") or "").strip().lower() == normalized_type]
    return filtered


def _build_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"all": len(rows), "queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
    for row in rows:
        status = normalize_task_status(row.get("status"))
        counts[status] = counts.get(status, 0) + 1
        if status == "queued":
            counts["running"] += 1
    return counts


def _resolve_task_for_user(user_id: str, task_id: str) -> Optional[Dict[str, Any]]:
    audit_snapshot = get_job_snapshot(task_id)
    if audit_snapshot and str(audit_snapshot.get("user_id") or "").strip() == user_id:
        return _map_audit_task(audit_snapshot)

    task = get_task(task_id)
    if not task:
        return None
    if str(task.get("user_id") or "").strip() != user_id:
        return None
    if str(task.get("task_type") or "").strip().lower() == "ppt":
        try:
            refreshed = refresh_presenton_task_record(task_id)
        except Exception:
            refreshed = None
        if refreshed:
            task = refreshed
    if str(task.get("task_type") or "").strip().lower() == "ocr":
        detailed = get_ocr_task_detail(task_id)
        if detailed:
            task = detailed
    return task


@router.get("/overview")
def list_task_overview(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None),
    ctx: Dict[str, Any] = Depends(require_active_user),
):
    all_rows = _merge_all_tasks(ctx["user_id"])
    filtered_rows = _filter_rows(all_rows, status=status, task_type=task_type)
    paged_rows = filtered_rows[offset : offset + limit]
    return {
        "success": True,
        "data": [_compact_task(row) for row in paged_rows],
        "meta": {
            "total": len(filtered_rows),
            "counts": _build_counts(all_rows),
            "limit": limit,
            "offset": offset,
            "status": normalize_task_status(status) if status else None,
            "task_type": str(task_type or "").strip().lower() or None,
        },
    }


@router.get("/overview/{task_id}")
def get_task_overview_detail(
    task_id: str,
    ctx: Dict[str, Any] = Depends(require_active_user),
):
    task = _resolve_task_for_user(ctx["user_id"], task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    compact = _compact_task(task)
    compact["detail"] = task.get("detail") or {}
    compact["raw"] = (
        task.get("raw")
        or compact["detail"].get("raw")
        or compact["detail"].get("raw_result")
        or compact["detail"].get("result")
    )
    return {"success": True, "data": compact}


@router.post("/overview/{task_id}/retry")
async def retry_task_overview(
    task_id: str,
    ctx: Dict[str, Any] = Depends(require_active_user),
):
    audit_snapshot = get_job_snapshot(task_id)
    if audit_snapshot and str(audit_snapshot.get("user_id") or "").strip() == ctx["user_id"]:
        ok, message, new_job = retry_audit_job_with_result(task_id)
        if not ok or not new_job:
            raise HTTPException(status_code=400, detail=message or "Retry failed")
        task = _map_audit_task(new_job)
        return {"success": True, "data": _compact_task(task)}

    task = get_task(task_id)
    if not task or str(task.get("user_id") or "").strip() != ctx["user_id"]:
        raise HTTPException(status_code=404, detail="Task not found")

    task_type = str(task.get("task_type") or "").strip().lower()
    if task_type == "voice":
        new_task = await retry_voice_task(task_id)
        compact = _compact_task(new_task)
        return {"success": True, "data": compact}
    if task_type == "ppt":
        new_task = retry_presenton_task(task_id)
        refreshed = _resolve_task_for_user(ctx["user_id"], str(new_task.get("task_id") or "").strip()) or new_task
        return {"success": True, "data": _compact_task(refreshed)}
    if task_type == "ocr":
        ok, message, new_task = retry_ocr_task(task_id)
        if not ok or not new_task:
            raise HTTPException(status_code=400, detail=message or "Retry failed")
        return {"success": True, "data": _compact_task(new_task)}

    raise HTTPException(status_code=400, detail="This task type does not support retry")
