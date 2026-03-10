import json
import re
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
from audit_pipeline import get_job_snapshot, cancel_audit_job, retry_audit_job, list_local_audit_jobs
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


class CreateUserPayload(BaseModel):
    account: str
    password: str
    role: str = "user"
    name: Optional[str] = None


def _load_rules_file(doc_type: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rules_dir = os.path.join(base_dir, "rules")
    file_path = os.path.join(rules_dir, f"{doc_type}_rules.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Rule file not found")
    return file_path


AUDIT_DOC_TYPE_LABELS = {
    "contract": "合同",
    "invoice": "发票",
    "payment": "付款单",
    "expense": "报销单",
    "packing_list": "装箱单",
    "bill_of_lading": "提单",
    "air_waybill": "空运运单",
    "import_declaration": "进口报关单",
    "export_declaration": "出口报关单",
    "certificate_of_origin": "原产地证",
    "trade_case": "贸易单据包",
    "auto": "自动识别",
}


def _audit_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _audit_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_finding_levels(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = {"high": 0, "medium": 0, "low": 0}
    for item in findings or []:
        if not isinstance(item, dict):
            continue
        severity = _audit_text(item.get("severity")).lower()
        if severity in stats:
            stats[severity] += 1
    stats["total"] = sum(stats.values())
    return stats


def _count_erp_checks(checks: List[Dict[str, Any]]) -> Dict[str, int]:
    total = 0
    passed = 0
    for item in checks or []:
        if not isinstance(item, dict):
            continue
        total += 1
        if item.get("passed") is True:
            passed += 1
    return {
        "total": total,
        "passed": passed,
        "failed": max(total - passed, 0),
    }


def _derive_audit_record_title(job: Dict[str, Any], result: Dict[str, Any], fields: Dict[str, Any]) -> str:
    explicit_title = _audit_text(fields.get("contract_title") or fields.get("project_name") or fields.get("subject"))
    if explicit_title:
        return explicit_title
    doc_no = _audit_text(fields.get("contract_no") or fields.get("invoice_no") or fields.get("application_no"))
    if doc_no:
        return doc_no
    file_name = _audit_text(job.get("file_name"))
    if file_name:
        return os.path.splitext(file_name)[0]
    subtype_label = _audit_text(result.get("recognized_doc_subtype_label"))
    if subtype_label:
        return subtype_label
    doc_type = _audit_text(job.get("doc_type")).lower()
    return f"{AUDIT_DOC_TYPE_LABELS.get(doc_type, doc_type or '审单')}记录"


def _build_audit_record_payload(job: Dict[str, Any], result: Dict[str, Any], review: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    review = review if isinstance(review, dict) else None
    fields = result.get("extracted_fields") if isinstance(result.get("extracted_fields"), dict) else {}
    erp_context = result.get("erp_context") if isinstance(result.get("erp_context"), dict) else {}
    case_summary = result.get("case_summary") if isinstance(result.get("case_summary"), dict) else {}
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    erp_checks = result.get("erp_checks") if isinstance(result.get("erp_checks"), list) else []
    title = _derive_audit_record_title(job, result, fields)
    company_name = _audit_text(fields.get("vendor") or fields.get("payee") or erp_context.get("expected_vendor"))
    counterparty_name = _audit_text(
        fields.get("buyer")
        or fields.get("customer")
        or fields.get("payer")
        or fields.get("drawer")
    )
    document_number = _audit_text(
        fields.get("contract_no")
        or fields.get("invoice_no")
        or fields.get("application_no")
        or fields.get("tax_no")
    )
    document_date = _audit_text(
        fields.get("contract_date")
        or fields.get("invoice_date")
        or fields.get("payment_date")
        or fields.get("expense_date")
        or fields.get("sign_date")
        or fields.get("issue_date")
    )
    amount = _audit_float(fields.get("total_amount"))
    finding_stats = _count_finding_levels(findings)
    check_stats = _count_erp_checks(erp_checks)
    first_finding = findings[0] if findings and isinstance(findings[0], dict) else {}
    risk_level = _audit_text(result.get("risk_level")).lower() or "low"
    workflow_state = _audit_text(result.get("workflow_state") or job.get("workflow_state") or job.get("status"))
    return {
        "job_id": job.get("job_id"),
        "user_id": job.get("user_id"),
        "file_name": _audit_text(job.get("file_name")),
        "doc_type": job.get("doc_type"),
        "doc_type_label": AUDIT_DOC_TYPE_LABELS.get(_audit_text(job.get("doc_type")).lower(), _audit_text(job.get("doc_type")) or "未知类型"),
        "status": job.get("status"),
        "progress": job.get("progress"),
        "created_at": job.get("created_at"),
        "risk_level": risk_level,
        "summary": _audit_text(result.get("summary")),
        "review": review,
        "review_status": _audit_text(review.get("status")) if review else "",
        "review_updated_at": _audit_text(review.get("updated_at")) if review else "",
        "reviewer_id": _audit_text(review.get("reviewer_id")) if review else "",
        "document_title": title,
        "document_number": document_number,
        "document_date": document_date,
        "company_name": company_name,
        "counterparty_name": counterparty_name,
        "amount": amount,
        "currency": _audit_text(fields.get("currency") or "CNY"),
        "audit_score": result.get("audit_score"),
        "headline": _audit_text(first_finding.get("message") or result.get("summary") or title),
        "next_action": _audit_text(result.get("next_action")),
        "workflow_state": workflow_state,
        "case_id": _audit_text(case_summary.get("case_id")),
        "case_document_count": len(case_summary.get("documents") or []),
        "finding_stats": finding_stats,
        "erp_check_stats": check_stats,
    }


def _audit_record_matches_query(record: Dict[str, Any], query: str) -> bool:
    keyword = _audit_text(query).lower()
    if not keyword:
        return True
    haystack = " ".join(
        [
            _audit_text(record.get("job_id")),
            _audit_text(record.get("user_id")),
            _audit_text(record.get("file_name")),
            _audit_text(record.get("document_title")),
            _audit_text(record.get("document_number")),
            _audit_text(record.get("company_name")),
            _audit_text(record.get("counterparty_name")),
            _audit_text(record.get("summary")),
            _audit_text(record.get("headline")),
            _audit_text(record.get("reviewer_id")),
        ]
    ).lower()
    return keyword in haystack


def _list_merged_audit_jobs(
    *,
    limit: int,
    offset: int,
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    jobs_by_id: Dict[str, Dict[str, Any]] = {}
    sb = require_supabase()
    try:
        db_query = sb.table("audit_jobs").select("*").order("created_at", desc=True).range(0, max(limit + offset + 200, 500) - 1)
        if user_id:
            db_query = db_query.eq("user_id", user_id)
        if doc_type:
            db_query = db_query.eq("doc_type", doc_type)
        if status:
            db_query = db_query.eq("status", status)
        db_rows = db_query.execute().data or []
    except Exception as e:
        print(f"[Admin Audit] Load audit_jobs failed: {e}")
        db_rows = []

    for row in db_rows:
        job_id = _audit_text(row.get("job_id"))
        if not job_id:
            continue
        jobs_by_id[job_id] = dict(row)

    local_rows = list_local_audit_jobs(limit=max(limit + offset + 200, 500), offset=0)
    for row in local_rows:
        job_id = _audit_text(row.get("job_id"))
        if not job_id:
            continue
        if user_id and _audit_text(row.get("user_id")) != _audit_text(user_id):
            continue
        if doc_type and _audit_text(row.get("doc_type")).lower() != _audit_text(doc_type).lower():
            continue
        if status and _audit_text(row.get("status")).lower() != _audit_text(status).lower():
            continue
        existing = jobs_by_id.get(job_id)
        if existing:
            merged = dict(row)
            merged.update(existing)
            for key in ("file_name", "workflow_state", "case_id", "result", "local_path"):
                if not merged.get(key) and row.get(key):
                    merged[key] = row.get(key)
            jobs_by_id[job_id] = merged
        else:
            jobs_by_id[job_id] = dict(row)

    jobs = list(jobs_by_id.values())
    jobs.sort(
        key=lambda item: (
            _audit_text(item.get("created_at") or item.get("updated_at")),
            _audit_text(item.get("job_id")),
        ),
        reverse=True,
    )
    if offset:
        jobs = jobs[offset:]
    return jobs[:limit]


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
        # 后备：仅从配置文件中列出（服务角色可能不可用）
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


def _account_to_email_and_phone(account: str) -> tuple[str, Optional[str]]:
    raw = (account or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Account is required")
    if "@" in raw:
        return raw.lower(), None
    phone = re.sub(r"\D+", "", raw)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid account format")
    return f"{phone}@flowus.cn", phone


@router.post("/users")
def create_user(
    payload: CreateUserPayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    account = (payload.account or "").strip()
    password = str(payload.password or "")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    role = _normalize_role(payload.role or "user")
    if role not in {"user", "admin", "auditor", "kb_admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    email, phone = _account_to_email_and_phone(account)
    default_name = (payload.name or "").strip() or (f"User_{phone[-4:]}" if phone else email.split("@")[0])

    sb_admin = get_admin_supabase(fresh=True)
    user_meta = {"name": default_name, "username": default_name}
    if phone:
        user_meta["phone"] = phone

    try:
        created = sb_admin.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_meta,
                "app_metadata": {"role": role},
            }
        )
        user_obj = created.user if hasattr(created, "user") else created
        new_user_id = getattr(user_obj, "id", None)
        if not new_user_id:
            raise HTTPException(status_code=500, detail="User created but missing user id")
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg or "exists" in msg or "duplicate" in msg:
            raise HTTPException(status_code=409, detail="Account already exists")
        raise HTTPException(status_code=500, detail=f"Create user failed: {e}")

    now = datetime.now(timezone.utc).isoformat()
    safe_upsert_profile(
        {
            "id": new_user_id,
            "email": email,
            "role": role,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )

    log_admin_action(
        ctx["user_id"],
        "user.create",
        new_user_id,
        {"account": account, "email": email, "role": role},
    )
    return {
        "success": True,
        "data": {
            "id": new_user_id,
            "email": email,
            "phone": phone,
            "name": default_name,
            "role": role,
            "status": "active",
        },
    }


@router.post("/users/{user_id}/role")
def update_user_role(
    user_id: str,
    payload: RoleUpdatePayload,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    role = _normalize_role(payload.role)
    # 使用新的管理客户端以避免过时的身份验证会话状态。
    sb_admin = get_admin_supabase(fresh=True)
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
        # 后备：通过 SQL 更新 app_metadata（需要数据库密码）
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
    # 使用新的管理客户端以避免过时的身份验证会话状态。
    sb_admin = get_admin_supabase(fresh=True)
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
        # 后备：通过 SQL 删除（需要数据库密码）
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

    purged = {
        "profiles": False,
        "documents": False,
        "history": False,
        "session_titles": False,
        "share_links": False,
        "share_snapshots": False,
    }

    try:
        sb.table("history").delete().eq("user_id", user_id).execute()
        purged["history"] = True
    except Exception:
        pass

    try:
        sb.table("session_titles").delete().eq("user_id", user_id).execute()
        purged["session_titles"] = True
    except Exception:
        pass

    try:
        links_res = sb.table("share_links").select("id").eq("owner_user_id", user_id).execute()
        link_ids = [row.get("id") for row in (links_res.data or []) if row.get("id") is not None]
        if link_ids:
            try:
                sb.table("share_snapshots").delete().in_("share_link_id", link_ids).execute()
                purged["share_snapshots"] = True
            except Exception:
                pass
        sb.table("share_links").delete().eq("owner_user_id", user_id).execute()
        purged["share_links"] = True
    except Exception:
        pass

    try:
        sb.table("profiles").delete().eq("id", user_id).execute()
        purged["profiles"] = True
    except Exception:
        pass

    try:
        sb.table("documents").delete().eq("metadata->>user_id", user_id).execute()
        purged["documents"] = True
    except Exception:
        pass

    log_admin_action(ctx["user_id"], "user.delete", user_id, purged)
    return {"success": True}


@router.get("/audit/records")
def list_audit_records(
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    status: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    search = query
    jobs = _list_merged_audit_jobs(
        limit=limit,
        offset=offset,
        user_id=user_id,
        doc_type=doc_type,
        status=status,
    )
    job_ids = [_audit_text(j.get("job_id")) for j in jobs if _audit_text(j.get("job_id"))]

    results_map = {}
    review_map = {}
    if job_ids:
        sb = require_supabase()
        try:
            r_res = sb.table("audit_results").select("job_id,result_json").in_("job_id", job_ids).execute()
            for row in r_res.data or []:
                results_map[row["job_id"]] = row.get("result_json")
        except Exception as e:
            print(f"[Admin Audit] Load audit_results failed: {e}")

        try:
            review_res = sb.table("audit_reviews").select("*").in_("job_id", job_ids).execute()
            for row in review_res.data or []:
                review_map[row["job_id"]] = row
        except Exception as e:
            print(f"[Admin Audit] Load audit_reviews failed: {e}")

    out = []
    for job in jobs:
        job_id = _audit_text(job.get("job_id"))
        result = results_map.get(job_id)
        if not isinstance(result, dict):
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
        review = review_map.get(job_id)
        risk = _audit_text((result or {}).get("risk_level")).lower()
        if risk_level and risk != _audit_text(risk_level).lower():
            continue
        row = _build_audit_record_payload(job, result, review)
        if not _audit_record_matches_query(row, search or ""):
            continue
        out.append(row)
    return {
        "success": True,
        "data": out,
        "meta": {
            "count": len(out),
            "offset": offset,
            "limit": limit,
            "has_more": len(jobs) >= limit,
        },
    }


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
    jobs = _list_merged_audit_jobs(limit=limit, offset=offset)
    return {"success": True, "data": jobs}


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
