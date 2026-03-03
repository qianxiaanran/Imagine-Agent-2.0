from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from workflow_manager import (
    SCENARIO_MONTHLY,
    confirm_workflow_job,
    get_workflow_job,
    list_workflow_jobs,
    retry_workflow_job,
    start_monthly_analysis,
)

router = APIRouter(prefix="/api/workflow", tags=["Workflow"])


class StartWorkflowPayload(BaseModel):
    scenario: str = Field(default=SCENARIO_MONTHLY)
    query: str
    user_id: str
    session_id: Optional[str] = None
    model_backend: Optional[str] = "local"
    topic: Optional[str] = None
    title: Optional[str] = None


class ConfirmWorkflowPayload(BaseModel):
    user_id: str
    action: str = Field(default="approved", description="approved | rejected")
    comment: Optional[str] = None


class RetryWorkflowPayload(BaseModel):
    user_id: str


@router.post("/jobs/start")
def start_job(payload: StartWorkflowPayload):
    scenario = str(payload.scenario or "").strip().lower()
    if scenario != SCENARIO_MONTHLY:
        raise HTTPException(status_code=400, detail=f"Unsupported scenario: {scenario}")
    try:
        data = start_monthly_analysis(
            user_id=payload.user_id,
            session_id=payload.session_id,
            query=payload.query,
            model_backend=payload.model_backend or "local",
            topic=payload.topic,
            title=payload.title,
        )
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
def list_jobs(user_id: str = Query(...), limit: int = Query(20, ge=1, le=100)):
    try:
        data = list_workflow_jobs(user_id=user_id, limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user_id: str = Query(...)):
    try:
        data = get_workflow_job(job_id=job_id, user_id=user_id)
        if not data:
            raise HTTPException(status_code=404, detail="Workflow job not found")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/confirm")
def confirm_job(job_id: str, payload: ConfirmWorkflowPayload):
    try:
        data = confirm_workflow_job(
            job_id=job_id,
            user_id=payload.user_id,
            action=payload.action,
            comment=payload.comment,
        )
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, payload: RetryWorkflowPayload):
    try:
        data = retry_workflow_job(job_id=job_id, user_id=payload.user_id)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

