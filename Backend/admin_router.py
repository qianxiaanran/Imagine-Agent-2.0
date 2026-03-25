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
from audit_pipeline import (
    get_job_snapshot,
    get_case_report,
    cancel_audit_job,
    retry_audit_job,
    list_local_audit_jobs,
    resolve_case_job_ids,
    _parse_date,
)
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
    case_id: Optional[str] = None
    apply_to_case: Optional[bool] = None


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
        "updated_at": job.get("updated_at"),
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
    child_doc_types = record.get("child_doc_types") if isinstance(record.get("child_doc_types"), list) else []
    child_file_names = record.get("child_file_names") if isinstance(record.get("child_file_names"), list) else []
    child_job_ids = record.get("child_job_ids") if isinstance(record.get("child_job_ids"), list) else []
    haystack = " ".join(
        [
            _audit_text(record.get("job_id")),
            _audit_text(record.get("case_id")),
            _audit_text(record.get("user_id")),
            _audit_text(record.get("file_name")),
            _audit_text(record.get("document_title")),
            _audit_text(record.get("document_number")),
            _audit_text(record.get("company_name")),
            _audit_text(record.get("counterparty_name")),
            _audit_text(record.get("summary")),
            _audit_text(record.get("headline")),
            _audit_text(record.get("reviewer_id")),
            " ".join(_audit_text(value) for value in child_doc_types),
            " ".join(_audit_text(value) for value in child_file_names),
            " ".join(_audit_text(value) for value in child_job_ids),
        ]
    ).lower()
    return keyword in haystack


def _normalize_review_filter(value: Optional[str]) -> Optional[str]:
    normalized = _audit_text(value).lower()
    if normalized in {"approved", "rejected", "need_more", "pending"}:
        return normalized
    return None


def _record_matches_filters(
    record: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    review_status: Optional[str] = None,
    query: Optional[str] = None,
) -> bool:
    if user_id and _audit_text(record.get("user_id")) != _audit_text(user_id):
        return False
    normalized_doc_type = _audit_text(doc_type).lower()
    if normalized_doc_type:
        if _audit_text(record.get("group_type")).lower() == "case":
            child_doc_types = {
                _audit_text(value).lower()
                for value in (record.get("child_doc_types") if isinstance(record.get("child_doc_types"), list) else [])
                if _audit_text(value)
            }
            if child_doc_types and normalized_doc_type not in child_doc_types:
                return False
            if not child_doc_types and _audit_text(record.get("doc_type")).lower() != normalized_doc_type:
                return False
        elif _audit_text(record.get("doc_type")).lower() != normalized_doc_type:
            return False
    if status and _audit_text(record.get("status")).lower() != _audit_text(status).lower():
        return False
    if risk_level and _audit_text(record.get("risk_level")).lower() != _audit_text(risk_level).lower():
        return False

    normalized_review = _normalize_review_filter(review_status)
    review_value = _audit_text(record.get("review_status")).lower()
    if normalized_review == "pending":
        if review_value:
            return False
    elif normalized_review and review_value != normalized_review:
        return False

    if query and not _audit_record_matches_query(record, query):
        return False
    return True


def _merge_audit_record_payload(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(primary or {})
    for key, value in (fallback or {}).items():
        if key not in merged:
            merged[key] = value
            continue
        current = merged.get(key)
        if current in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
            continue
        if isinstance(current, dict) and not current and isinstance(value, dict):
            merged[key] = value
    return merged


def _review_payload_from_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = _audit_text(row.get("review_status"))
    comment = row.get("review_comment")
    reviewer_id = row.get("reviewer_id")
    updated_at = row.get("review_updated_at")
    created_at = row.get("review_created_at")
    if not any([status, comment, reviewer_id, updated_at, created_at]):
        return None
    return {
        "status": status,
        "comment": comment,
        "reviewer_id": reviewer_id,
        "updated_at": updated_at,
        "created_at": created_at,
    }


def _resolve_review_scope(job_id: str, *, case_id: Optional[str] = None, apply_to_case: Optional[bool] = None) -> Dict[str, Any]:
    normalized_job_id = _audit_text(job_id)
    snapshot = get_job_snapshot(normalized_job_id) or {}
    effective_case_id = _audit_text(case_id or snapshot.get("case_id"))
    allow_case_scope = apply_to_case is not False
    job_ids = [normalized_job_id] if normalized_job_id else []
    if allow_case_scope and effective_case_id:
        case_job_ids = resolve_case_job_ids(effective_case_id, include_job_id=normalized_job_id)
        if len(case_job_ids) > 1:
            job_ids = case_job_ids
    return {
        "type": "case" if len(job_ids) > 1 else "job",
        "case_id": effective_case_id or None,
        "job_ids": job_ids,
        "affected_count": len(job_ids),
    }


def _save_review_row(
    sb: Any,
    *,
    job_id: str,
    status: str,
    comment: Optional[str],
    reviewer_id: str,
    now: str,
) -> None:
    existing = sb.table("audit_reviews").select("id,created_at").eq("job_id", job_id).limit(1).execute()
    row = existing.data[0] if existing.data else None
    payload = {
        "job_id": job_id,
        "status": status,
        "comment": comment,
        "reviewer_id": reviewer_id,
        "updated_at": now,
    }
    if row and row.get("id") is not None:
        sb.table("audit_reviews").update(payload).eq("id", row["id"]).execute()
        return
    payload["created_at"] = now
    sb.table("audit_reviews").insert(payload).execute()


def _risk_rank(value: Any) -> int:
    normalized = _audit_text(value).lower()
    if normalized == "high":
        return 3
    if normalized == "medium":
        return 2
    if normalized == "low":
        return 1
    return 0


def _status_rank(value: Any) -> int:
    normalized = _audit_text(value).lower()
    if normalized == "failed":
        return 4
    if normalized == "running":
        return 3
    if normalized == "pending":
        return 2
    if normalized == "done":
        return 1
    return 0


def _pick_latest_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {}
    return sorted(
        records,
        key=lambda item: (
            _audit_text(item.get("created_at") or item.get("document_date")),
            _audit_text(item.get("job_id")),
        ),
        reverse=True,
    )[0]


def _pick_common_text(records: List[Dict[str, Any]], key: str) -> str:
    values = [
        _audit_text(record.get(key))
        for record in records
        if _audit_text(record.get(key))
    ]
    if not values:
        return ""
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (item[1], len(item[0]), item[0]), reverse=True)[0][0]


def _aggregate_review_status(records: List[Dict[str, Any]]) -> str:
    statuses = [_audit_text(record.get("review_status")).lower() for record in records if _audit_text(record.get("review_status"))]
    if not statuses:
        return ""
    if len(statuses) < len(records):
        return ""
    unique = set(statuses)
    if len(unique) == 1:
        return statuses[0]
    if "need_more" in unique:
        return "need_more"
    if "rejected" in unique:
        return "rejected"
    return ""


def _aggregate_case_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest = _pick_latest_record(records)
    if not latest:
        return {}

    case_id = _audit_text(latest.get("case_id"))
    doc_count = len(records)
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    status_values: List[str] = []
    review_values: List[str] = []
    total_findings = 0
    total_checks = 0
    passed_checks = 0
    best_amount: Optional[float] = None
    score_values: List[float] = []
    child_labels: List[str] = []
    child_doc_types: List[str] = []
    child_file_names: List[str] = []

    for record in records:
        risk_value = _audit_text(record.get("risk_level")).lower() or "low"
        if risk_value in risk_counts:
            risk_counts[risk_value] += 1
        status_value = _audit_text(record.get("status")).lower()
        if status_value:
            status_values.append(status_value)
        review_value = _audit_text(record.get("review_status")).lower()
        if review_value:
            review_values.append(review_value)
        finding_stats = record.get("finding_stats") if isinstance(record.get("finding_stats"), dict) else {}
        check_stats = record.get("erp_check_stats") if isinstance(record.get("erp_check_stats"), dict) else {}
        total_findings += int(finding_stats.get("total") or 0)
        total_checks += int(check_stats.get("total") or 0)
        passed_checks += int(check_stats.get("passed") or 0)
        numeric_amount = _audit_float(record.get("amount"))
        if numeric_amount is not None and (best_amount is None or numeric_amount > best_amount):
            best_amount = numeric_amount
        numeric_score = _audit_float(record.get("audit_score"))
        if numeric_score is not None:
            score_values.append(numeric_score)
        child_label = _audit_text(record.get("file_name") or record.get("document_title"))
        if child_label and child_label not in child_labels:
            child_labels.append(child_label)
        child_file_name = _audit_text(record.get("file_name"))
        if child_file_name and child_file_name not in child_file_names:
            child_file_names.append(child_file_name)
        child_doc_type = _audit_text(record.get("doc_type")).lower()
        if child_doc_type and child_doc_type not in child_doc_types:
            child_doc_types.append(child_doc_type)

    aggregated_risk = max(((_audit_text(record.get("risk_level")).lower() or "low") for record in records), key=_risk_rank, default="low")
    aggregated_status = max(((_audit_text(record.get("status")).lower() or "done") for record in records), key=_status_rank, default="done")
    aggregated_review = _aggregate_review_status(records)
    representative_title = _pick_common_text(records, "company_name") or _pick_common_text(records, "document_title")
    headline_parts = [
        f"共 {doc_count} 份单据",
        f"高风险 {risk_counts['high']} 份",
        f"中风险 {risk_counts['medium']} 份",
        f"低风险 {risk_counts['low']} 份",
    ]
    if child_labels:
        headline_parts.append(f"包含：{' / '.join(child_labels[:3])}")

    aggregate = dict(latest)
    aggregate.update({
        "group_type": "case",
        "doc_type": "trade_case",
        "doc_type_label": "Case",
        "document_title": f"Case {case_id}" if case_id else f"整包汇总 · {doc_count}份单据",
        "document_number": case_id or _audit_text(latest.get("document_number")),
        "file_name": f"整包汇总 · {doc_count}份单据",
        "risk_level": aggregated_risk,
        "status": aggregated_status,
        "review_status": aggregated_review,
        "case_document_count": max(int(latest.get("case_document_count") or 0), doc_count),
        "finding_stats": {
            "high": risk_counts["high"],
            "medium": risk_counts["medium"],
            "low": risk_counts["low"],
            "total": total_findings,
        },
        "erp_check_stats": {
            "total": total_checks,
            "passed": passed_checks,
            "failed": max(total_checks - passed_checks, 0),
        },
        "headline": "；".join(headline_parts),
        "summary": "；".join(headline_parts),
        "amount": best_amount,
        "audit_score": round(min(score_values), 2) if score_values else latest.get("audit_score"),
        "company_name": representative_title or _pick_common_text(records, "company_name"),
        "counterparty_name": _pick_common_text(records, "counterparty_name"),
        "child_doc_types": child_doc_types,
        "child_file_names": child_file_names,
        "child_job_ids": [_audit_text(record.get("job_id")) for record in records if _audit_text(record.get("job_id"))],
        "review": None,
    })
    return aggregate


def _group_audit_records(records: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    normalized_mode = _audit_text(mode).lower()
    if normalized_mode != "case":
        return list(records)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        case_id = _audit_text(record.get("case_id"))
        job_id = _audit_text(record.get("job_id"))
        group_key = f"case:{case_id}" if case_id else f"job:{job_id}"
        grouped.setdefault(group_key, []).append(record)

    output: List[Dict[str, Any]] = []
    for values in grouped.values():
        latest = _pick_latest_record(values)
        case_id = _audit_text(latest.get("case_id"))
        if case_id:
            output.append(_aggregate_case_record(values))
        else:
            item = dict(latest)
            item["group_type"] = "job"
            output.append(item)
    return output


def _build_audit_record_stats(records: List[Dict[str, Any]]) -> Dict[str, int]:
    normalized_records = [record for record in records if isinstance(record, dict)]
    return {
        "total": len(normalized_records),
        "high": sum(1 for record in normalized_records if _audit_text(record.get("risk_level")).lower() == "high"),
        "pending": sum(
            1
            for record in normalized_records
            if not _audit_text(record.get("review_status"))
            or _audit_text(record.get("review_status")).lower() == "need_more"
        ),
        "approved": sum(1 for record in normalized_records if _audit_text(record.get("review_status")).lower() == "approved"),
    }


def _load_latest_review_rows(job_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    normalized_job_ids = [_audit_text(value) for value in job_ids if _audit_text(value)]
    if not normalized_job_ids:
        return {}
    try:
        sb = require_supabase()
        rows = (
            sb.table("audit_reviews")
            .select("job_id,status,comment,reviewer_id,updated_at,created_at")
            .in_("job_id", normalized_job_ids)
            .order("updated_at", desc=True)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
    except Exception as e:
        print(f"[Admin Audit] Load review rows failed: {e}")
        return {}

    latest_by_job: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        job_id = _audit_text(row.get("job_id"))
        if not job_id or job_id in latest_by_job:
            continue
        latest_by_job[job_id] = dict(row)
    return latest_by_job


def _aggregate_review_payload(review_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized_rows = [dict(row) for row in review_rows if isinstance(row, dict)]
    if not normalized_rows:
        return None

    statuses = [_audit_text(row.get("status")).lower() for row in normalized_rows if _audit_text(row.get("status"))]
    comments = [_audit_text(row.get("comment")) for row in normalized_rows if _audit_text(row.get("comment"))]
    latest = sorted(
        normalized_rows,
        key=lambda row: (
            _audit_text(row.get("updated_at") or row.get("created_at")),
            _audit_text(row.get("job_id")),
        ),
        reverse=True,
    )[0]
    status = _aggregate_review_status([{"review_status": value} for value in statuses]) if statuses else ""
    comment = ""
    if comments:
        if len(set(comments)) == 1:
            comment = comments[0]
        else:
            comment = _audit_text(latest.get("comment"))

    if not any([status, comment, latest.get("reviewer_id"), latest.get("updated_at"), latest.get("created_at")]):
        return None
    return {
        "status": status,
        "comment": comment,
        "reviewer_id": latest.get("reviewer_id"),
        "updated_at": latest.get("updated_at"),
        "created_at": latest.get("created_at"),
    }


def _build_case_detail_job(job: Dict[str, Any], case_report: Dict[str, Any], review_scope: Dict[str, Any]) -> Dict[str, Any]:
    case_summary = case_report.get("case_summary") if isinstance(case_report.get("case_summary"), dict) else {}
    case_documents = case_summary.get("documents") if isinstance(case_summary.get("documents"), list) else []
    case_id = _audit_text(case_summary.get("case_id") or job.get("case_id") or review_scope.get("case_id"))
    count = len(case_documents)
    detail_job = dict(job or {})
    detail_job.update({
        "case_id": case_id,
        "doc_type": "trade_case",
        "group_type": "case",
        "file_name": f"整包汇总 · {count}份单据" if count else (_audit_text(job.get("file_name")) or "整包汇总"),
        "workflow_state": case_report.get("workflow_state") or job.get("workflow_state"),
        "status": job.get("status") or "done",
        "case_documents": case_documents,
        "case_document_count": count,
        "result": case_report,
    })
    return detail_job


def _build_audit_record_from_db_row(row: Dict[str, Any]) -> Dict[str, Any]:
    job = {key: value for key, value in dict(row or {}).items() if not str(key).startswith("review_") and key != "result_json"}
    result = row.get("result_json") if isinstance(row.get("result_json"), dict) else {}
    review = _review_payload_from_row(row)
    return _build_audit_record_payload(job, result, review)


def _load_db_audit_record_rows(
    *,
    limit: int,
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    review_status: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    fetch_limit = max(50, min(int(limit or 0), 2000))
    normalized_query = _audit_text(query).lower()
    query_like = f"%{normalized_query}%"
    normalized_review = _normalize_review_filter(review_status)
    normalized_risk = _audit_text(risk_level).lower() or None

    sql = text(
        """
        SELECT
            j.*,
            r.result_json,
            rv.status AS review_status,
            rv.comment AS review_comment,
            rv.reviewer_id AS reviewer_id,
            rv.updated_at AS review_updated_at,
            rv.created_at AS review_created_at
        FROM audit_jobs AS j
        LEFT JOIN audit_results AS r
            ON r.job_id = j.job_id
        LEFT JOIN LATERAL (
            SELECT status, comment, reviewer_id, updated_at, created_at
            FROM audit_reviews
            WHERE audit_reviews.job_id = j.job_id
            ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
            LIMIT 1
        ) AS rv ON TRUE
        WHERE (:user_id = '' OR j.user_id = :user_id)
          AND (:doc_type = '' OR LOWER(COALESCE(j.doc_type, '')) = :doc_type)
          AND (:status = '' OR LOWER(COALESCE(j.status, '')) = :status)
          AND (:risk_level = '' OR LOWER(COALESCE(r.result_json ->> 'risk_level', '')) = :risk_level)
          AND (
                :review_status = ''
                OR (:review_status = 'pending' AND COALESCE(rv.status, '') = '')
                OR (:review_status <> 'pending' AND LOWER(COALESCE(rv.status, '')) = :review_status)
              )
          AND (
                :query_like = ''
                OR LOWER(COALESCE(CAST(j.job_id AS TEXT), '')) LIKE :query_like
                OR LOWER(COALESCE(j.user_id, '')) LIKE :query_like
                OR LOWER(COALESCE(j.file_name, '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json ->> 'summary', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json ->> 'headline', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json ->> 'recognized_doc_subtype_label', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'vendor', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'payee', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'buyer', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'customer', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'contract_no', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'invoice_no', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'application_no', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'subject', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'contract_title', '')) LIKE :query_like
                OR LOWER(COALESCE(r.result_json -> 'extracted_fields' ->> 'project_name', '')) LIKE :query_like
              )
        ORDER BY COALESCE(j.created_at, j.updated_at) DESC NULLS LAST, j.job_id DESC
        LIMIT :fetch_limit
        """
    )

    try:
        with engine.begin() as conn:
            return [dict(row) for row in conn.execute(
                sql,
                {
                    "user_id": _audit_text(user_id),
                    "doc_type": _audit_text(doc_type).lower(),
                    "status": _audit_text(status).lower(),
                    "risk_level": normalized_risk or "",
                    "review_status": normalized_review or "",
                    "query_like": query_like if normalized_query else "",
                    "fetch_limit": fetch_limit,
                },
            ).mappings().all()]
    except Exception as e:
        print(f"[Admin Audit] SQL audit record query failed: {e}")
        return []


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
        fetch_limit = max(limit + offset + 40, 200)
        db_query = sb.table("audit_jobs").select("*").order("created_at", desc=True).range(0, fetch_limit - 1)
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
    review_status: Optional[str] = None,
    query: Optional[str] = None,
    group_by: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN, ROLE_AUDITOR])),
):
    _ = ctx
    search = _audit_text(query)
    group_mode = _audit_text(group_by).lower()
    group_by_case = group_mode == "case"
    fetch_window = min(
        max((offset + limit + (80 if group_by_case else 120)) * (6 if group_by_case else 1), 240),
        5000 if group_by_case else 2000,
    )

    db_rows = _load_db_audit_record_rows(
        limit=fetch_window,
        user_id=user_id,
        doc_type=None if group_by_case else doc_type,
        status=None if group_by_case else status,
        risk_level=None if group_by_case else risk_level,
        review_status=None if group_by_case else review_status,
        query=None if group_by_case else search,
    )
    records_by_id: Dict[str, Dict[str, Any]] = {}
    for row in db_rows:
        record = _build_audit_record_from_db_row(row)
        if not group_by_case and not _record_matches_filters(
            record,
            user_id=user_id,
            doc_type=doc_type,
            status=status,
            risk_level=risk_level,
            review_status=review_status,
            query=search,
        ):
            continue
        job_id = _audit_text(record.get("job_id"))
        if job_id:
            records_by_id[job_id] = record

    local_rows = list_local_audit_jobs(limit=fetch_window, offset=0)
    for local_job in local_rows:
        local_record = _build_audit_record_payload(
            local_job,
            local_job.get("result") if isinstance(local_job.get("result"), dict) else {},
            None,
        )
        if not group_by_case and not _record_matches_filters(
            local_record,
            user_id=user_id,
            doc_type=doc_type,
            status=status,
            risk_level=risk_level,
            review_status=review_status,
            query=search,
        ):
            continue
        job_id = _audit_text(local_record.get("job_id"))
        if not job_id:
            continue
        existing = records_by_id.get(job_id)
        if not existing:
            records_by_id[job_id] = local_record
            continue
        existing_updated = _parse_date(existing.get("updated_at") or existing.get("created_at"))
        local_updated = _parse_date(local_record.get("updated_at") or local_record.get("created_at"))
        prefer_local = existing_updated is None or (local_updated is not None and local_updated >= existing_updated)
        primary = local_record if prefer_local else existing
        fallback = existing if prefer_local else local_record
        records_by_id[job_id] = _merge_audit_record_payload(primary, fallback)

    all_records = list(records_by_id.values())
    stats_scope_records = list(all_records)
    if group_by_case:
        all_records = _group_audit_records(all_records, "case")
        stats_scope_records = [
            record
            for record in all_records
            if _record_matches_filters(
                record,
                user_id=user_id,
                doc_type=doc_type,
                query=search,
            )
        ]
        all_records = [
            record
            for record in stats_scope_records
            if _record_matches_filters(
                record,
                user_id=user_id,
                doc_type=doc_type,
                status=status,
                risk_level=risk_level,
                review_status=review_status,
                query=search,
            )
        ]
    stats = _build_audit_record_stats(stats_scope_records)
    all_records.sort(
        key=lambda item: (
            _audit_text(item.get("created_at") or item.get("document_date")),
            _audit_text(item.get("job_id")),
        ),
        reverse=True,
    )
    page_rows = all_records[offset: offset + limit]
    has_more = len(all_records) > (offset + limit)
    return {
        "success": True,
        "data": page_rows,
        "meta": {
            "count": len(page_rows),
            "total_visible": len(all_records),
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "stats": stats,
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
    review_scope = _resolve_review_scope(job_id, case_id=job.get("case_id"), apply_to_case=True)
    target_job_ids = review_scope.get("job_ids") if isinstance(review_scope.get("job_ids"), list) else [job_id]
    review_map = _load_latest_review_rows(target_job_ids)
    review_row = _aggregate_review_payload(list(review_map.values()))

    if review_scope.get("type") == "case" and _audit_text(review_scope.get("case_id")):
        case_report = get_case_report(_audit_text(review_scope.get("case_id")))
        if case_report:
            case_job = _build_case_detail_job(job, case_report, review_scope)
            return {"success": True, "data": {"job": case_job, "review": review_row, "review_scope": review_scope}}

    return {"success": True, "data": {"job": job, "review": review_row, "review_scope": review_scope}}


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
    review_scope = _resolve_review_scope(
        payload.job_id,
        case_id=payload.case_id,
        apply_to_case=payload.apply_to_case,
    )
    target_job_ids = review_scope.get("job_ids") or []
    if not target_job_ids:
        raise HTTPException(status_code=404, detail="Job not found")

    for target_job_id in target_job_ids:
        _save_review_row(
            sb,
            job_id=target_job_id,
            status=status,
            comment=payload.comment,
            reviewer_id=ctx["user_id"],
            now=now,
        )

    log_admin_action(
        ctx["user_id"],
        "audit.review",
        payload.case_id or payload.job_id,
        {
            "status": status,
            "scope": review_scope.get("type"),
            "affected_count": review_scope.get("affected_count"),
            "case_id": review_scope.get("case_id"),
        },
    )
    return {"success": True, "scope": review_scope}


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
