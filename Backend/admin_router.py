# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from pydantic import BaseModel

from admin_utils import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_KB_ADMIN,
    require_role,
    log_admin_action,
    _normalize_role,
    safe_upsert_profile,
)
from supabase_client import get_admin_supabase, require_supabase, engine
from audit_pipeline import get_job_snapshot, cancel_audit_job, retry_audit_job
from documents_processing import get_embeddings

router = APIRouter(prefix="/api/admin", tags=["Admin"])


class RoleUpdatePayload(BaseModel):
    role: str


class StatusUpdatePayload(BaseModel):
    status: str


class ForceLogoutPayload(BaseModel):
    reason: Optional[str] = None


class AuditReviewPayload(BaseModel):
    job_id: str
    status: str
    comment: Optional[str] = None


class RuleUpdatePayload(BaseModel):
    rules: List[Dict[str, Any]]


class KbGovernancePayload(BaseModel):
    source: str
    user_id: str
    status: str


class KbDeletePayload(BaseModel):
    source: str
    user_id: str


class KbReindexPayload(BaseModel):
    source: str
    user_id: str


def _load_rules_file(doc_type: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rules_dir = os.path.join(base_dir, "rules")
    file_path = os.path.join(rules_dir, f"{doc_type}_rules.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Rule file not found")
    return file_path


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    query: Optional[str] = None,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    sb = require_supabase()
    results = []
    try:
        sb_admin = get_admin_supabase()
        response = sb_admin.auth.admin.list_users(page=page, per_page=per_page)
        users = response.users if hasattr(response, "users") else response
        users = users or []

        user_ids = [u.id for u in users]
        profiles = {}
        if user_ids:
            try:
                prof_res = sb.table("profiles").select("*").in_("id", user_ids).execute()
                for row in prof_res.data or []:
                    profiles[row["id"]] = row
            except Exception:
                profiles = {}

        for u in users:
            email = (u.email or "") if hasattr(u, "email") else ""
            meta = getattr(u, "user_metadata", {}) or {}
            app_meta = getattr(u, "app_metadata", {}) or {}
            role = _normalize_role(app_meta.get("role"))
            profile = profiles.get(u.id, {})
            status = profile.get("status", "active")
            row = {
                "id": u.id,
                "email": email,
                "phone": meta.get("phone"),
                "name": meta.get("name") or meta.get("username") or email,
                "role": role,
                "status": status,
                "created_at": getattr(u, "created_at", None),
                "last_sign_in_at": getattr(u, "last_sign_in_at", None),
                "department": profile.get("department"),
                "job_title": profile.get("job_title"),
            }
            if query:
                q = query.lower()
                hay = f"{row['email']} {row['phone']} {row['name']}".lower()
                if q not in hay:
                    continue
            results.append(row)
    except Exception:
        # fallback: list from profiles only (service role may not be available)
        try:
            prof_query = sb.table("profiles").select("*").order("created_at", desc=True).range((page - 1) * per_page, page * per_page - 1)
            if query:
                prof_query = prof_query.or_(f"email.ilike.%{query}%,id.ilike.%{query}%,role.ilike.%{query}%")
            prof_res = prof_query.execute()
            rows = prof_res.data or []
        except Exception:
            try:
                prof_query = sb.table("profiles").select("*").range((page - 1) * per_page, page * per_page - 1)
                if query:
                    prof_query = prof_query.or_(f"id.ilike.%{query}%,role.ilike.%{query}%")
                prof_res = prof_query.execute()
                rows = prof_res.data or []
            except Exception:
                prof_query = sb.table("profiles").select("*").range((page - 1) * per_page, page * per_page - 1)
                prof_res = prof_query.execute()
                rows = prof_res.data or []
        for row in rows:
            results.append({
                "id": row.get("id"),
                "email": row.get("email"),
                "phone": row.get("phone"),
                "name": row.get("name") or row.get("email") or row.get("id"),
                "role": row.get("role", "user"),
                "status": row.get("status", "active"),
                "created_at": row.get("created_at"),
                "last_sign_in_at": row.get("last_login_at"),
                "department": row.get("department"),
                "job_title": row.get("job_title"),
            })

    return {"success": True, "data": results}


@router.post("/users/{user_id}/role")
def update_user_role(
    user_id: str,
    payload: RoleUpdatePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    role = _normalize_role(payload.role)
    sb_admin = get_admin_supabase()
    email = None
    try:
        user_res = sb_admin.auth.admin.get_user_by_id(user_id)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=404, detail="User not found")

        app_meta = user_res.user.app_metadata or {}
        app_meta["role"] = role
        sb_admin.auth.admin.update_user_by_id(user_id, {"app_metadata": app_meta})
        email = user_res.user.email
    except HTTPException:
        raise
    except Exception:
        # fallback: update app_metadata via SQL (requires DB password)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "update auth.users "
                        "set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) "
                        "|| jsonb_build_object('role', :role) "
                        "where id = :uid"
                    ),
                    {"role": role, "uid": user_id},
                )
        except Exception as db_err:
            raise HTTPException(
                status_code=403,
                detail=f"Service role key invalid and DB fallback failed: {db_err}",
            )

    now = datetime.now(timezone.utc).isoformat()
    safe_upsert_profile({
        "id": user_id,
        "email": email,
        "role": role,
        "updated_at": now,
        "created_at": now,
        "status": "active",
    })

    log_admin_action(ctx["user_id"], "user.set_role", user_id, {"role": role})
    return {"success": True}


@router.post("/users/{user_id}/status")
def update_user_status(
    user_id: str,
    payload: StatusUpdatePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    status = payload.status.strip().lower()
    if status not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    safe_upsert_profile({
        "id": user_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    log_admin_action(ctx["user_id"], "user.set_status", user_id, {"status": status})
    return {"success": True}


@router.post("/users/{user_id}/force_logout")
def force_logout(
    user_id: str,
    payload: Optional[ForceLogoutPayload] = None,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    now = datetime.now(timezone.utc).isoformat()
    safe_upsert_profile({
        "id": user_id,
        "force_logout_at": now,
        "updated_at": now,
    })
    reason = payload.reason if payload else None
    log_admin_action(ctx["user_id"], "user.force_logout", user_id, {"reason": reason})
    return {"success": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    if ctx.get("user_id") == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete current user")

    sb = require_supabase()
    sb_admin = get_admin_supabase()
    delete_ok = False

    try:
        delete_fn = getattr(sb_admin.auth.admin, "delete_user", None)
        if callable(delete_fn):
            delete_fn(user_id)
            delete_ok = True
        else:
            delete_fn = getattr(sb_admin.auth.admin, "delete_user_by_id", None)
            if callable(delete_fn):
                delete_fn(user_id)
                delete_ok = True
    except Exception:
        delete_ok = False

    if not delete_ok:
        # fallback: delete via SQL (requires DB password)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("delete from auth.users where id = :uid"),
                    {"uid": user_id},
                )
            delete_ok = True
        except Exception as db_err:
            raise HTTPException(
                status_code=403,
                detail=f"Service role key invalid and DB fallback failed: {db_err}",
            )

    try:
        sb.table("profiles").delete().eq("id", user_id).execute()
    except Exception:
        pass

    try:
        sb.table("documents").delete().eq("metadata->>user_id", user_id).execute()
    except Exception:
        pass

    log_admin_action(ctx["user_id"], "user.delete", user_id, {"purge_profile": True, "purge_documents": True})
    return {"success": True}


@router.get("/audit/records")
def list_audit_records(
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    sb = require_supabase()
    query = sb.table("audit_jobs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    if user_id:
        query = query.eq("user_id", user_id)
    if doc_type:
        query = query.eq("doc_type", doc_type)
    if status:
        query = query.eq("status", status)
    res = query.execute()
    jobs = res.data or []
    job_ids = [j["job_id"] for j in jobs]

    results_map = {}
    review_map = {}
    if job_ids:
        r_res = sb.table("audit_results").select("job_id,result_json").in_("job_id", job_ids).execute()
        for row in r_res.data or []:
            results_map[row["job_id"]] = row.get("result_json")

        review_res = sb.table("audit_reviews").select("*").in_("job_id", job_ids).execute()
        for row in review_res.data or []:
            review_map[row["job_id"]] = row

    out = []
    for job in jobs:
        result = results_map.get(job["job_id"], {})
        review = review_map.get(job["job_id"])
        risk = (result or {}).get("risk_level")
        if risk_level and risk != risk_level:
            continue
        out.append({
            "job_id": job["job_id"],
            "user_id": job.get("user_id"),
            "doc_type": job.get("doc_type"),
            "status": job.get("status"),
            "progress": job.get("progress"),
            "created_at": job.get("created_at"),
            "risk_level": risk,
            "summary": (result or {}).get("summary"),
            "review": review,
        })
    return {"success": True, "data": out}


@router.get("/audit/records/{job_id}")
def audit_record_detail(
    job_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    sb = require_supabase()
    review = sb.table("audit_reviews").select("*").eq("job_id", job_id).limit(1).execute()
    review_row = review.data[0] if review.data else None
    return {"success": True, "data": {"job": job, "review": review_row}}


@router.post("/audit/review")
def audit_review(
    payload: AuditReviewPayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    status = payload.status.strip().lower()
    if status not in ("approved", "rejected", "need_more"):
        raise HTTPException(status_code=400, detail="Invalid review status")
    sb = require_supabase()
    now = datetime.now(timezone.utc).isoformat()
    sb.table("audit_reviews").upsert({
        "job_id": payload.job_id,
        "status": status,
        "comment": payload.comment,
        "reviewer_id": ctx["user_id"],
        "updated_at": now,
        "created_at": now,
    }).execute()
    log_admin_action(ctx["user_id"], "audit.review", payload.job_id, {"status": status})
    return {"success": True}


@router.get("/audit/rules/{doc_type}")
def get_audit_rules(
    doc_type: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    file_path = _load_rules_file(doc_type)
    with open(file_path, "r", encoding="utf-8") as f:
        return {"success": True, "data": json.load(f)}


@router.put("/audit/rules/{doc_type}")
def update_audit_rules(
    doc_type: str,
    payload: RuleUpdatePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    file_path = _load_rules_file(doc_type)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload.rules, f, ensure_ascii=False, indent=2)
    log_admin_action(ctx["user_id"], "audit.rules.update", doc_type, {"count": len(payload.rules)})
    return {"success": True}


@router.get("/jobs")
def list_jobs(
    job_type: str = "audit",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    if job_type != "audit":
        return {"success": True, "data": []}
    sb = require_supabase()
    res = sb.table("audit_jobs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"success": True, "data": res.data or []}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    ok = cancel_audit_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    log_admin_action(ctx["user_id"], "jobs.cancel", job_id, None)
    return {"success": True}


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    ok, msg = retry_audit_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg or "Retry failed")
    log_admin_action(ctx["user_id"], "jobs.retry", job_id, None)
    return {"success": True}


@router.get("/kb/documents")
def list_kb_documents(
    limit: int = Query(200, ge=1, le=1000),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_KB_ADMIN])),
):
    sb = require_supabase()
    try:
        docs_res = sb.table("documents").select("id, metadata, created_at").order("created_at", desc=True).limit(limit).execute()
        docs = docs_res.data or []
    except Exception:
        try:
            docs_res = sb.table("documents").select("id, metadata, updated_at").order("updated_at", desc=True).limit(limit).execute()
            docs = docs_res.data or []
        except Exception:
            docs_res = sb.table("documents").select("id, metadata").limit(limit).execute()
            docs = docs_res.data or []
    items: Dict[str, Dict[str, Any]] = {}
    for row in docs:
        meta = row.get("metadata") or {}
        source = meta.get("source") or "unknown"
        user_id = meta.get("user_id") or "unknown"
        key = f"{user_id}::{source}"
        item = items.get(key)
        created_at = row.get("created_at") or row.get("updated_at")
        if not item:
            items[key] = {
                "source": source,
                "user_id": user_id,
                "chunk_count": 1,
                "last_updated": created_at,
            }
        else:
            item["chunk_count"] += 1
            if created_at and (not item.get("last_updated") or created_at > item["last_updated"]):
                item["last_updated"] = created_at

    governance = sb.table("kb_governance").select("*").execute().data or []
    gov_map = {f"{g['user_id']}::{g['source']}": g for g in governance}

    out = []
    for key, item in items.items():
        gov = gov_map.get(key)
        out.append({
            **item,
            "status": (gov or {}).get("status", "pending"),
            "updated_at": (gov or {}).get("updated_at"),
        })
    return {"success": True, "data": out}


@router.post("/kb/documents/approve")
def approve_kb_document(
    payload: KbGovernancePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_KB_ADMIN])),
):
    status = payload.status.strip().lower()
    if status not in ("approved", "rejected", "archived", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    sb = require_supabase()
    now = datetime.now(timezone.utc).isoformat()
    sb.table("kb_governance").upsert({
        "source": payload.source,
        "user_id": payload.user_id,
        "status": status,
        "updated_at": now,
        "created_at": now,
    }).execute()
    log_admin_action(ctx["user_id"], "kb.set_status", f"{payload.user_id}:{payload.source}", {"status": status})
    return {"success": True}


@router.post("/kb/documents/delete")
def delete_kb_document(
    payload: KbDeletePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_KB_ADMIN])),
):
    sb = require_supabase()
    sb.table("documents").delete().eq("metadata->>source", payload.source).eq("metadata->>user_id", payload.user_id).execute()
    log_admin_action(ctx["user_id"], "kb.delete", f"{payload.user_id}:{payload.source}", None)
    return {"success": True}


@router.post("/kb/documents/reindex")
def reindex_kb_document(
    payload: KbReindexPayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_KB_ADMIN])),
):
    sb = require_supabase()
    docs_res = sb.table("documents").select("id, content, metadata").eq("metadata->>source", payload.source).eq("metadata->>user_id", payload.user_id).execute()
    docs = docs_res.data or []
    if not docs:
        return {"success": False, "error": "No documents found"}
    embeddings = get_embeddings()
    texts = [d.get("content", "") for d in docs]
    vectors = embeddings.embed_documents(texts)
    for doc, vector in zip(docs, vectors):
        sb.table("documents").update({"embedding": vector}).eq("id", doc["id"]).execute()
    log_admin_action(ctx["user_id"], "kb.reindex", f"{payload.user_id}:{payload.source}", {"chunks": len(docs)})
    return {"success": True, "count": len(docs)}


@router.get("/logs")
def list_admin_logs(
    limit: int = Query(100, ge=1, le=500),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    sb = require_supabase()
    res = sb.table("admin_audit_logs").select("*").order("created_at", desc=True).limit(limit).execute()
    return {"success": True, "data": res.data or []}
