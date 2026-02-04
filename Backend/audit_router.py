from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from audit_pipeline import enqueue_audit_job, get_job_snapshot

router = APIRouter(tags=["Audit"])


@router.post("/api/audit/start")
async def audit_start(
    file: UploadFile = File(...),
    doc_type: str = Form(None),
    user_id: str = Form(None),
):
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    job = enqueue_audit_job(file_bytes, file.filename, user_id or "anonymous", doc_type)
    return {"job_id": job["job_id"], "status": job["status"]}


@router.get("/api/audit/{job_id}")
def audit_status(job_id: str):
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
