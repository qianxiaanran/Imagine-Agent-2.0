import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse

from audit_pipeline import (
    _resolve_audit_local_path,
    enqueue_audit_job,
    get_case_report,
    get_job_snapshot,
    push_audit_action_to_erp,
)

router = APIRouter(tags=["Audit"])


class AuditErpActionPayload(BaseModel):
    action: str
    operator_id: str | None = None
    comment: str | None = None


@router.post("/api/audit/start")
async def audit_start(
    file: UploadFile = File(...),
    doc_type: str = Form(None),
    user_id: str = Form(None),
    case_id: str = Form(None),
    model_type: str = Form(None),
    client_request_id: str = Form(None),
):
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        job = enqueue_audit_job(
            file_bytes,
            file.filename,
            user_id or "anonymous",
            doc_type,
            case_id=case_id,
            model_type=model_type,
            client_request_id=client_request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Audit queue unavailable: {e}")
    snapshot = get_job_snapshot(job["job_id"]) or {}
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "result_link": f"/tasks?task={job['job_id']}",
        "case_id": job.get("case_id"),
        "file_url": snapshot.get("file_url") or job.get("file_url"),
        "file_name": snapshot.get("file_name") or job.get("file_name"),
        "stage": job.get("stage"),
        "workflow_state": snapshot.get("workflow_state") or job.get("workflow_state"),
        "upload_sequence_notice": job.get("upload_sequence_notice") or snapshot.get("upload_sequence_notice"),
        "case_documents": snapshot.get("case_documents", []),
        "client_request_id": job.get("client_request_id"),
    }


@router.get("/api/audit/{job_id}")
def audit_status(job_id: str):
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/api/public/audit/source")
def audit_source_file(
    file_url: str | None = None,
    file_name: str | None = None,
    job_id: str | None = None,
):
    snapshot = get_job_snapshot(job_id) if job_id else None
    resolved_file_url = file_url or (snapshot or {}).get("file_url")
    resolved_file_name = file_name or (snapshot or {}).get("file_name")
    if not resolved_file_url:
        raise HTTPException(status_code=400, detail="Missing audit file path")

    local_path = _resolve_audit_local_path(
        resolved_file_url,
        user_id=(snapshot or {}).get("user_id"),
        job_id=job_id or (snapshot or {}).get("job_id"),
        file_name=resolved_file_name,
        local_path_hint=(snapshot or {}).get("local_path"),
    )
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="Audit source file not found")

    download_name = resolved_file_name or os.path.basename(local_path) or "document"
    return FileResponse(path=local_path, filename=download_name)


@router.get("/api/audit/case/{case_id}")
def audit_case_report(case_id: str):
    result = get_case_report(case_id)
    if not result:
        raise HTTPException(status_code=404, detail="Case not found")
    case_summary = result.get("case_summary") if isinstance(result, dict) else {}
    return {
        "case_id": case_id,
        "status": "done",
        "workflow_state": result.get("workflow_state"),
        "case_documents": (case_summary or {}).get("documents", []),
        "result": result,
    }


@router.post("/api/audit/{job_id}/erp-action")
def audit_erp_action(job_id: str, payload: AuditErpActionPayload):
    ok, data = push_audit_action_to_erp(
        job_id=job_id,
        action=payload.action,
        operator_id=payload.operator_id or "system",
        comment=payload.comment,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=data.get("error", "ERP writeback failed"))
    return {"success": True, **data}
