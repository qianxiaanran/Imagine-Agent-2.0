from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from audit_pipeline import enqueue_audit_job, get_job_snapshot, push_audit_action_to_erp

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
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Audit queue unavailable: {e}")
    snapshot = get_job_snapshot(job["job_id"]) or {}
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "case_id": job.get("case_id"),
        "stage": job.get("stage"),
        "case_documents": snapshot.get("case_documents", []),
    }


@router.get("/api/audit/{job_id}")
def audit_status(job_id: str):
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
