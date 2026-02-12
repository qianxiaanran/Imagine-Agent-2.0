import json
import os
import re
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, ValidationError, Field

try:
    from ocr_manager import OCRManager
except Exception:
    OCRManager = None

try:
    from documents_processing import load_documents
except Exception:
    load_documents = None

try:
    from deepseek_llm import ask_llm
except Exception:
    ask_llm = None
try:
    from deepseek_llm import get_llm_instance
    from langchain.schema import HumanMessage, SystemMessage
except Exception:
    get_llm_instance = None
    HumanMessage = None
    SystemMessage = None

try:
    from supabase_client import require_supabase
except Exception:
    require_supabase = None
try:
    from erp_adapter import get_erp_adapter, get_supported_erp_providers
except Exception:
    get_erp_adapter = None
    get_supported_erp_providers = None

try:
    from queue_manager import AUDIT_QUEUE_NAME, enqueue_job
except Exception:
    AUDIT_QUEUE_NAME = os.getenv("AUDIT_QUEUE_NAME", "audit_tasks")
    enqueue_job = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_STORAGE_ROOT = os.path.join(BASE_DIR, "storage", "audit")
RULES_DIR = os.path.join(BASE_DIR, "rules")
AI_MAX_TEXT_CHARS = 4000
AI_MAX_FINDINGS = 6
AUDIT_AI_BACKEND = os.getenv("AUDIT_AI_BACKEND", "local")
AUDIT_LLM_ENABLED = os.getenv("AUDIT_LLM_ENABLED", "true").lower() != "false"
AUDIT_LLM_BACKEND = os.getenv("AUDIT_LLM_BACKEND", AUDIT_AI_BACKEND)
AUDIT_LLM_MAX_CHARS = int(os.getenv("AUDIT_LLM_MAX_CHARS", "6000"))
AUDIT_HISTORY_LIMIT = int(os.getenv("AUDIT_HISTORY_LIMIT", "200"))
AUDIT_FEEDBACK_LIMIT = int(os.getenv("AUDIT_FEEDBACK_LIMIT", "120"))
ANOMALY_MIN_SAMPLES = int(os.getenv("AUDIT_ANOMALY_MIN_SAMPLES", "5"))
ERP_PROVIDER = os.getenv("AUDIT_ERP_PROVIDER", "mock")
ERP_ACTION_TABLES = ["audit_erp_actions", "erp_audit_actions"]
ERP_ACTIONS = {"approved", "rejected", "need_more"}
RISK_WEIGHT = {"high": 25, "medium": 12, "low": 5}
AUDIT_JOB_TIMEOUT_SECONDS = int(os.getenv("AUDIT_JOB_TIMEOUT_SECONDS", "5400"))
AUDIT_JOB_RETRY_MAX = int(os.getenv("AUDIT_JOB_RETRY_MAX", "2"))

DOC_TYPE_ALIASES = {
    "auto": "auto",
    "自动识别": "auto",
    "invoice": "invoice",
    "发票": "invoice",
    "contract": "contract",
    "合同": "contract",
    "payment": "payment",
    "付款单": "payment",
    "expense": "expense",
    "报销单": "expense",
}

STAGE_PROGRESS = {
    "pending": 0,
    "ocr": 30,
    "extract": 55,
    "rules": 70,
    "ai": 85,
    "report": 95,
    "done": 100,
    "failed": 100,
}

AUDIT_JOBS: Dict[str, Dict[str, Any]] = {}
AUDIT_LOCK = threading.Lock()
_OCR_ENGINE: Optional[OCRManager] = None


class AuditFields(BaseModel):
    doc_type: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    invoice_no: Optional[str] = None
    tax_no: Optional[str] = None
    vendor: Optional[str] = None
    contract_no: Optional[str] = None
    contract_date: Optional[str] = None
    invoice_date: Optional[str] = None
    payment_date: Optional[str] = None
    payee: Optional[str] = None
    bank_account: Optional[str] = None
    reimburser: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class AuditAIFinding(BaseModel):
    type: Optional[str] = None
    severity: Optional[str] = None
    message: Optional[str] = None
    reason: Optional[str] = None
    suggestion: Optional[str] = None
    action: Optional[str] = None
    confidence: Optional[float] = None
    decision_mode: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(extra="allow")


class AuditAIAssessment(BaseModel):
    risk_level: Optional[str] = "low"
    pass_: Optional[bool] = Field(default=None, alias="pass")
    summary: Optional[str] = None
    findings: List[AuditAIFinding] = []
    confidence: Optional[float] = None
    model_config = ConfigDict(populate_by_name=True, extra="allow")


def normalize_doc_type(doc_type: Optional[str]) -> str:
    key = (doc_type or "").strip()
    if not key:
        return "auto"
    return DOC_TYPE_ALIASES.get(key, DOC_TYPE_ALIASES.get(key.lower(), "auto"))


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = _safe_text(value).lower()
    return text in {"1", "true", "yes", "y", "on", "ok", "black", "blocked", "high"}


def _parse_date(value: Any) -> Optional[datetime]:
    text = _safe_text(value)
    if not text:
        return None
    candidates = []
    m = re.search(r"(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})", text)
    if m:
        candidates.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", text)
    if m:
        candidates.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    candidates.append(text.replace("/", "-"))
    for item in candidates:
        try:
            return datetime.fromisoformat(item)
        except Exception:
            continue
    return None


def _get_ocr_engine() -> Optional[OCRManager]:
    global _OCR_ENGINE
    if _OCR_ENGINE is None and OCRManager:
        _OCR_ENGINE = OCRManager()
    return _OCR_ENGINE


def _ensure_storage_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _save_local_file(file_bytes: bytes, user_id: str, job_id: str, filename: str) -> Tuple[str, str]:
    safe_name = filename.replace("\\", "_").replace("/", "_")
    target_dir = os.path.join(LOCAL_STORAGE_ROOT, user_id, job_id)
    _ensure_storage_dir(target_dir)
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    relative_path = f"audit/{user_id}/{job_id}/{safe_name}"
    return target_path, relative_path


def _insert_db(table: str, payload: Any) -> None:
    if not require_supabase:
        return
    try:
        sb = require_supabase()
        sb.table(table).insert(payload).execute()
    except Exception as e:
        print(f"[Audit DB] Insert failed ({table}): {e}")


def _update_db(table: str, payload: Dict[str, Any], job_id: str, key: str = "job_id") -> None:
    if not require_supabase:
        return
    try:
        sb = require_supabase()
        sb.table(table).update(payload).eq(key, job_id).execute()
    except Exception as e:
        print(f"[Audit DB] Update failed ({table}): {e}")


def _load_job_from_db(job_id: str) -> Optional[Dict[str, Any]]:
    if not require_supabase:
        return None
    try:
        sb = require_supabase()
        job_resp = sb.table("audit_jobs").select("*").eq("job_id", job_id).limit(1).execute()
        if not job_resp.data:
            return None
        job = job_resp.data[0]
        file_url = job.get("file_url")
        file_name = job.get("file_name")
        if not file_name and file_url:
            file_name = os.path.basename(str(file_url))
        result_resp = sb.table("audit_results").select("result_json").eq("job_id", job_id).limit(1).execute()
        result = result_resp.data[0]["result_json"] if result_resp.data else None
        return {
            "job_id": job.get("job_id"),
            "user_id": job.get("user_id"),
            "doc_type": job.get("doc_type"),
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "stage": job.get("stage"),
            "error_message": job.get("error_message"),
            "file_url": file_url,
            "file_name": file_name,
            "result": result,
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }
    except Exception as e:
        print(f"[Audit DB] Load job failed: {e}")
        return None


def create_job(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    doc_type: Optional[str],
) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    normalized_doc_type = normalize_doc_type(doc_type)
    safe_user_id = user_id or "anonymous"

    _, file_url = _save_local_file(file_bytes, safe_user_id, job_id, filename)
    file_url = file_url.replace("\\", "/")

    job = {
        "job_id": job_id,
        "doc_id": doc_id,
        "user_id": safe_user_id,
        "doc_type": normalized_doc_type,
        "status": "pending",
        "progress": 0,
        "stage": "pending",
        "error_message": None,
        "file_url": file_url,
        "file_name": filename,
        "result": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    with AUDIT_LOCK:
        AUDIT_JOBS[job_id] = job

    _insert_db("audit_jobs", {
        "job_id": job_id,
        "user_id": safe_user_id,
        "doc_type": normalized_doc_type,
        "status": "pending",
        "progress": 0,
        "stage": "pending",
        "error_message": None,
        "file_url": file_url,
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    })
    _insert_db("audit_docs", {
        "doc_id": doc_id,
        "job_id": job_id,
        "doc_type": normalized_doc_type,
        "file_url": file_url,
        "created_at": job["created_at"],
    })

    return job


def update_job(job_id: str, **updates: Any) -> None:
    now_iso = _now_iso()
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if job:
            job.update(updates)
            job["updated_at"] = now_iso

    payload = {k: v for k, v in updates.items() if k != "result"}
    if payload:
        payload["updated_at"] = now_iso
        _update_db("audit_jobs", payload, job_id)


def _is_cancelled(job_id: str) -> bool:
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if job and job.get("cancelled"):
            return True
    snapshot = _load_job_from_db(job_id)
    if not snapshot:
        return False
    status = str(snapshot.get("status") or "").lower()
    stage = str(snapshot.get("stage") or "").lower()
    return status == "cancelled" or stage == "cancelled"


def cancel_audit_job(job_id: str) -> bool:
    found = False
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if job:
            found = True
            job["cancelled"] = True
            job["status"] = "cancelled"
            job["stage"] = "cancelled"
            job["progress"] = 100
            job["updated_at"] = _now_iso()

    snapshot = _load_job_from_db(job_id)
    if snapshot:
        found = True
    if not found:
        return False

    _update_db("audit_jobs", {
        "status": "cancelled",
        "stage": "cancelled",
        "progress": 100,
        "updated_at": _now_iso(),
    }, job_id)
    return True


def retry_audit_job(job_id: str) -> Tuple[bool, Optional[str]]:
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
    if not job:
        job = _load_job_from_db(job_id)
    if not job:
        return False, "Job not found"
    user_id = job.get("user_id") or "anonymous"
    file_url = job.get("file_url")
    file_name = job.get("file_name") or os.path.basename(str(file_url or "")) or "document"
    if not file_url:
        return False, "Missing file path"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(base_dir, "storage", file_url.replace("/", os.sep))
    if not os.path.exists(local_path):
        return False, "File not found"
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        enqueue_audit_job(file_bytes, file_name, user_id, job.get("doc_type", "auto"))
        return True, None
    except Exception as e:
        return False, str(e)


def get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    snapshot = _load_job_from_db(job_id)
    if snapshot:
        return snapshot

    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if job:
            return {
                "job_id": job["job_id"],
                "user_id": job.get("user_id"),
                "status": job["status"],
                "progress": job.get("progress", 0),
                "stage": job.get("stage"),
                "error_message": job.get("error_message"),
                "result": job.get("result"),
                "doc_type": job.get("doc_type"),
                "file_url": job.get("file_url"),
                "file_name": job.get("file_name"),
            }
    return None


DATE_PATTERN = r"20\d{2}\s*(?:[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}|\u5e74\s*\d{1,2}\s*\u6708\s*\d{1,2}\s*\u65e5?)"


def _extract_dates(text: str) -> List[str]:
    dates = []
    for m in re.findall(DATE_PATTERN, text or ""):
        dates.append(m.strip())
    return dates


def _find_date_by_keywords(text: str, keywords: List[str]) -> Optional[str]:
    if not text:
        return None
    for kw in keywords:
        pattern = rf"{kw}\s*[:\uFF1A]?\s*({DATE_PATTERN})"
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None


def _extract_amounts(text: str) -> List[float]:
    amounts = []
    for m in re.findall(r"([0-9]+(?:,[0-9]{3})*(?:\.\d+)?)", text):
        val = _safe_float(m)
        if val is not None:
            amounts.append(val)
    return amounts


def _find_amount_by_keywords(text: str, keywords: List[str]) -> Optional[float]:
    for kw in keywords:
        pattern = rf"{kw}\s*[:：]?\s*([0-9]+(?:,[0-9]{{3}})*(?:\.\d+)?)"
        m = re.search(pattern, text)
        if m:
            return _safe_float(m.group(1))
    return None


AUDIT_DOC_TYPES = ["invoice", "contract", "payment", "expense"]
AUDIT_FIELD_KEYS = [
    "total_amount",
    "currency",
    "invoice_no",
    "tax_no",
    "vendor",
    "contract_no",
    "contract_date",
    "invoice_date",
    "payment_date",
    "payee",
    "bank_account",
    "reimburser",
]


def _truncate_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start:end + 1].strip()
    candidate = re.sub(r",\s*}", "}", candidate)
    candidate = re.sub(r",\s*]", "]", candidate)
    try:
        return json.loads(candidate)
    except Exception:
        repaired = re.sub(r"(?<!\\)'", '"', candidate)
        try:
            return json.loads(repaired)
        except Exception:
            return None


def _clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in ("null", "None", "N/A", "NA", "n/a", "无", "未知", "未填写"):
        return None
    text = re.sub(r"^[\s:：\-\(\)\[\]（）【】]+", "", text)
    text = re.sub(r"[\s:：\-\(\)\[\]（）【】]+$", "", text)
    return text or None


def _normalize_date_value(value: Any) -> Optional[str]:
    text = _clean_value(value)
    if not text:
        return None
    m = re.search(r"(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    date_match = re.search(DATE_PATTERN, text)
    return date_match.group(0).strip() if date_match else text


def _extract_with_llm(raw_text: str, hint_type: Optional[str] = None, llm_backend: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not AUDIT_LLM_ENABLED:
        return None
    if not ask_llm and not get_llm_instance:
        return None
    trimmed = _truncate_text(raw_text or "", AUDIT_LLM_MAX_CHARS)
    if not trimmed:
        return None
    backend = llm_backend or AUDIT_LLM_BACKEND
    doc_types_desc = "\n".join([f"- {key}" for key in AUDIT_DOC_TYPES])
    fields_desc = "\n".join([f"- {key}" for key in AUDIT_FIELD_KEYS])
    hint_note = f"提示：如果给定类型，请优先使用 {hint_type}。" if hint_type else ""
    system_prompt = "你是结构化抽取引擎，只输出严格 JSON。不要输出解释或 Markdown。"
    prompt = (
        "请从 OCR 文本中抽取智能审单字段。\n"
        "文档类型候选列表:\n"
        f"{doc_types_desc}\n\n"
        "字段 key 列表:\n"
        f"{fields_desc}\n\n"
        "输出要求:\n"
        "1) 只输出 JSON。\n"
        "2) JSON 结构为 {\"doc_type\":\"<type>\",\"fields\":{...}}。\n"
        "3) fields 仅包含上述字段 key，无法确定用空字符串。\n"
        "4) 日期格式为 YYYY-MM-DD，金额仅保留数字和小数点。\n"
        "5) 不要把冒号、括号等符号带入值。\n"
        f"{hint_note}\n\n"
        "OCR 文本:\n"
        f"{trimmed}\n"
    )
    try:
        response = None
        if get_llm_instance and SystemMessage and HumanMessage:
            llm = get_llm_instance(backend, temperature=0)
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
            resp = llm.invoke(messages)
            response = resp.content if hasattr(resp, "content") else str(resp)
        elif ask_llm:
            response = ask_llm(prompt, model_type=backend)
        else:
            return None
    except Exception:
        return None
    payload = _extract_json_payload(response)
    if not payload:
        return None
    doc_type = payload.get("doc_type")
    fields = payload.get("fields", {})
    return {"doc_type": doc_type, "fields": fields}


def _merge_llm_fields(base_fields: Dict[str, Any], llm_result: Optional[Dict[str, Any]], allow_doc_type_override: bool = False) -> Dict[str, Any]:
    if not llm_result:
        return base_fields
    merged = dict(base_fields)
    llm_doc_type = llm_result.get("doc_type")
    if allow_doc_type_override and llm_doc_type in AUDIT_DOC_TYPES:
        merged["doc_type"] = llm_doc_type
    llm_fields = llm_result.get("fields", {}) if isinstance(llm_result, dict) else {}
    for key in AUDIT_FIELD_KEYS:
        if key not in llm_fields:
            continue
        value = llm_fields.get(key)
        if key == "total_amount":
            amount = _safe_float(value)
            if amount is not None:
                merged[key] = amount
            continue
        if key in ("contract_date", "invoice_date", "payment_date"):
            date_val = _normalize_date_value(value)
            if date_val:
                merged[key] = date_val
            continue
        if key == "currency":
            cur = _clean_value(value)
            if cur:
                cur_up = cur.upper()
                if cur_up in ("CNY", "USD", "EUR", "RMB"):
                    merged[key] = "CNY" if cur_up == "RMB" else cur_up
            continue
        cleaned = _clean_value(value)
        if cleaned:
            merged[key] = cleaned
    return merged


def _extract_fields(raw_text: str, doc_type: str) -> Dict[str, Any]:
    text = raw_text or ""
    fields: Dict[str, Any] = {"doc_type": doc_type}

    currency = "CNY"
    if "USD" in text or "$" in text:
        currency = "USD"
    elif "EUR" in text or "€" in text:
        currency = "EUR"
    fields["currency"] = currency

    fields["invoice_no"] = None
    m = re.search(r"发票(号码|号)\s*[:：]?\s*([A-Za-z0-9\-]+)", text)
    if m:
        fields["invoice_no"] = m.group(2)

    m = re.search(r"(税号|纳税人识别号)\s*[:：]?\s*([0-9A-Za-z]{15,20})", text)
    if m:
        fields["tax_no"] = m.group(2)

    dates = _extract_dates(text)
    if dates:
        fields["invoice_date"] = dates[0]
        fields["payment_date"] = dates[-1]

    fields["contract_no"] = None
    m = re.search(r"合同(编号|号)\s*[:：]?\s*([A-Za-z0-9\-]+)", text)
    if m:
        fields["contract_no"] = m.group(2)

    fields["vendor"] = None
    m = re.search(r"(供应商|甲方|乙方|收款方)\s*[:：]?\s*([^\n\r]{2,40})", text)
    if m:
        fields["vendor"] = m.group(2).strip()

    total_amount = _find_amount_by_keywords(text, ["价税合计", "合计", "总计", "金额", "应付", "付款金额", "报销金额"])
    if total_amount is None:
        amounts = _extract_amounts(text)
        total_amount = max(amounts) if amounts else None
    fields["total_amount"] = total_amount

    m = re.search(r"(收款方|收款户名|收款单位)\s*[:：]?\s*([^\n\r]{2,40})", text)
    if m:
        fields["payee"] = m.group(2).strip()

    m = re.search(r"(银行账号|账号|开户账号)\s*[:：]?\s*([0-9]{8,30})", text)
    if m:
        fields["bank_account"] = m.group(2)

    m = re.search(r"(报销人|申请人)\s*[:：]?\s*([^\n\r]{2,20})", text)
    if m:
        fields["reimburser"] = m.group(2).strip()

    if doc_type == "contract":
        contract_date = _find_date_by_keywords(
            text,
            [
                "\u7b7e\u7f72\u65e5\u671f",
                "\u7b7e\u8ba2\u65e5\u671f",
                "\u5408\u540c\u65e5\u671f",
                "\u7b7e\u7f72\u65e5",
                "\u7b7e\u8ba2\u65e5",
            ],
        )
        if not contract_date and dates:
            contract_date = dates[0]
        if contract_date:
            fields["contract_date"] = contract_date

    llm_result = _extract_with_llm(text, doc_type, AUDIT_LLM_BACKEND)
    fields = _merge_llm_fields(fields, llm_result, allow_doc_type_override=False)

    return fields


def _infer_doc_type_llm(raw_text: str) -> Optional[str]:
    llm_result = _extract_with_llm(raw_text or "", None, AUDIT_LLM_BACKEND)
    if not llm_result:
        return None
    doc_type = llm_result.get("doc_type")
    return doc_type if doc_type in AUDIT_DOC_TYPES else None


def _infer_doc_type(raw_text: str) -> str:
    text = raw_text or ""
    if "发票" in text or "税号" in text or "开票" in text:
        return "invoice"
    if "合同" in text or "协议" in text or "签署" in text:
        return "contract"
    if "付款" in text or "收款" in text or "银行账号" in text:
        return "payment"
    if "报销" in text or "费用" in text or "差旅" in text:
        return "expense"
    return "invoice"


def _validate_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    try:
        parsed = AuditFields.model_validate(fields)
        return parsed.model_dump(exclude_none=True)
    except ValidationError:
        return fields


def _coerce_bool(value: Any) -> bool:
    return bool(value) and value not in ("0", 0, "false", "False")


def _resolve_path(ctx: Dict[str, Any], path: str) -> Any:
    if path.startswith("fields."):
        path = path[len("fields."):]
        base = ctx.get("fields", {})
    elif path.startswith("erp."):
        path = path[len("erp."):]
        base = ctx.get("erp", {})
    else:
        base = ctx.get("fields", {})
    cur = base
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _check_condition(cond: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    field = cond.get("field")
    op = cond.get("op", "exists")
    value = cond.get("value")
    value_field = cond.get("value_field")

    field_value = _resolve_path(ctx, field) if field else None
    other_value = _resolve_path(ctx, value_field) if value_field else value

    if op == "exists":
        return field_value is not None and field_value != ""
    if op == "missing":
        return field_value is None or field_value == ""
    if op == "missing_or_zero":
        return field_value in (None, "", 0, 0.0, "0")
    if op == "eq":
        return field_value == other_value
    if op == "neq":
        return field_value != other_value
    if op == "contains":
        return isinstance(field_value, str) and isinstance(other_value, str) and other_value in field_value
    if op == "not_contains":
        return isinstance(field_value, str) and isinstance(other_value, str) and other_value not in field_value
    if op == "regex":
        return isinstance(field_value, str) and re.search(str(other_value), field_value) is not None
    if op == "in":
        return field_value in (other_value or [])
    if op == "not_in":
        return field_value not in (other_value or [])
    if op == "gt":
        return _safe_float(field_value) is not None and _safe_float(field_value) > _safe_float(other_value)
    if op == "gte":
        return _safe_float(field_value) is not None and _safe_float(field_value) >= _safe_float(other_value)
    if op == "lt":
        return _safe_float(field_value) is not None and _safe_float(field_value) < _safe_float(other_value)
    if op == "lte":
        return _safe_float(field_value) is not None and _safe_float(field_value) <= _safe_float(other_value)
    if op == "gt_field":
        return _safe_float(field_value) is not None and _safe_float(field_value) > _safe_float(other_value)
    if op == "lt_field":
        return _safe_float(field_value) is not None and _safe_float(field_value) < _safe_float(other_value)
    if op == "truthy":
        return _coerce_bool(field_value)
    if op == "falsy":
        return not _coerce_bool(field_value)
    return False


def _load_rules(doc_type: str) -> List[Dict[str, Any]]:
    path = os.path.join(RULES_DIR, f"{doc_type}_rules.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Audit Rules] Load failed: {e}")
        return []


def _extract_snippet(text: str, keyword: str, window: int = 60) -> str:
    if not text or not keyword:
        return ""
    idx = text.find(keyword)
    if idx == -1:
        return text[:window * 2].strip()
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    return text[start:end].strip()


def _build_evidence(rule: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evidence = rule.get("evidence") or {}
    field = evidence.get("field")
    keyword = evidence.get("keyword")
    raw_text = ctx.get("raw_text", "")

    text = ""
    highlight = ""
    if field:
        value = _resolve_path(ctx, field)
        if value is not None:
            text = str(value)
            highlight = text
    if not text and keyword:
        text = _extract_snippet(raw_text, keyword)
        highlight = keyword
    if not text:
        return None
    return {"text": text, "highlight": highlight}


def _build_finding(
    *,
    source: str,
    decision_mode: str,
    finding_type: str,
    severity: str,
    message: str,
    reason: str,
    suggestion: str,
    evidence: Optional[Dict[str, Any]] = None,
    confidence: Optional[float] = None,
    rule_id: Optional[str] = None,
    action: Optional[str] = None,
) -> Dict[str, Any]:
    score = _safe_float(confidence)
    if score is None:
        score = 0.75 if decision_mode == "ai_semantic" else 0.98
    score = _clamp(score, 0.0, 1.0)
    return {
        "rule_id": rule_id,
        "source": source,
        "decision_mode": decision_mode,
        "type": finding_type,
        "severity": _normalize_severity(severity),
        "message": _safe_text(message) or "风险提示",
        "reason": _safe_text(reason) or _safe_text(message) or "命中风险条件",
        "suggestion": _safe_text(suggestion) or "建议人工复核",
        "action": _safe_text(action) or _safe_text(suggestion) or "建议人工复核",
        "evidence": evidence or None,
        "confidence": score,
    }


def _condition_to_text(cond: Dict[str, Any]) -> str:
    field = _safe_text(cond.get("field") or "字段")
    op = _safe_text(cond.get("op") or "exists")
    value = cond.get("value_field") if cond.get("value_field") is not None else cond.get("value")
    op_map = {
        "exists": "存在",
        "missing": "缺失",
        "missing_or_zero": "缺失或为0",
        "eq": "等于",
        "neq": "不等于",
        "contains": "包含",
        "not_contains": "不包含",
        "regex": "匹配",
        "in": "属于",
        "not_in": "不属于",
        "gt": "大于",
        "gte": "大于等于",
        "lt": "小于",
        "lte": "小于等于",
        "gt_field": "大于字段",
        "lt_field": "小于字段",
        "truthy": "为真",
        "falsy": "为假",
    }
    desc = op_map.get(op, op)
    if value is None or value == "":
        return f"{field}{desc}"
    return f"{field}{desc}{value}"


def _build_rule_reason(rule: Dict[str, Any], checks: List[Dict[str, Any]]) -> str:
    rule_id = _safe_text(rule.get("id") or "RULE")
    if checks:
        return f"规则 {rule_id} 命中：{'；'.join(_condition_to_text(c) for c in checks[:3])}"
    return f"规则 {rule_id} 命中"


def _run_rules(doc_type: str, fields: Dict[str, Any], raw_text: str, erp: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = _load_rules(doc_type)
    ctx = {"fields": fields, "raw_text": raw_text, "erp": erp}
    findings: List[Dict[str, Any]] = []

    for rule in rules:
        when = rule.get("when") or []
        checks = rule.get("checks") or []
        if isinstance(when, dict):
            when = [when]
        if isinstance(checks, dict):
            checks = [checks]

        if when:
            if not all(_check_condition(cond, ctx) for cond in when):
                continue

        failed = False
        if checks:
            for cond in checks:
                if _check_condition(cond, ctx):
                    failed = True
                    break
        else:
            failed = True

        if failed:
            reason = _safe_text(rule.get("reason")) or _build_rule_reason(rule, checks)
            suggestion = _safe_text(rule.get("suggestion")) or "建议人工复核"
            findings.append(
                _build_finding(
                    source="rule",
                    decision_mode="rule_hit",
                    finding_type="policy",
                    severity=rule.get("severity", "medium"),
                    message=_safe_text(rule.get("message") or "规则触发"),
                    reason=reason,
                    suggestion=suggestion,
                    action=suggestion,
                    evidence=_build_evidence(rule, ctx),
                    confidence=0.99,
                    rule_id=rule.get("id"),
                )
            )
    return findings


def _collect_history_records(user_id: str, limit: int = AUDIT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
    if not require_supabase:
        return []
    try:
        sb = require_supabase()
        jobs_res = (
            sb.table("audit_jobs")
            .select("job_id,doc_type,status,created_at")
            .eq("user_id", user_id)
            .eq("status", "done")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        jobs = jobs_res.data or []
        job_ids = [row.get("job_id") for row in jobs if row.get("job_id")]
        if not job_ids:
            return []

        result_res = sb.table("audit_results").select("job_id,result_json,created_at").in_("job_id", job_ids).execute()
        result_map = {
            row.get("job_id"): row.get("result_json") or {}
            for row in (result_res.data or [])
            if row.get("job_id")
        }

        records = []
        for job in jobs:
            job_id = job.get("job_id")
            result = result_map.get(job_id) or {}
            fields = result.get("extracted_fields") if isinstance(result, dict) else {}
            if not isinstance(fields, dict):
                fields = {}
            records.append(
                {
                    "job_id": job_id,
                    "doc_type": job.get("doc_type"),
                    "status": job.get("status"),
                    "created_at": job.get("created_at"),
                    "risk_level": result.get("risk_level"),
                    "summary": result.get("summary"),
                    "findings": result.get("findings") if isinstance(result.get("findings"), list) else [],
                    "fields": fields,
                    "result": result if isinstance(result, dict) else {},
                }
            )
        return records
    except Exception as e:
        print(f"[Audit History] Load failed: {e}")
        return []


def _collect_review_feedback(
    user_id: str,
    doc_type: str,
    history_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    feedback = {
        "reviewed_count": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "need_more_count": 0,
        "false_positive_hints": [],
        "false_negative_hints": [],
        "review_notes": [],
    }
    if not require_supabase:
        return feedback

    try:
        sb = require_supabase()
        query = (
            sb.table("audit_jobs")
            .select("job_id,doc_type")
            .eq("user_id", user_id)
            .eq("status", "done")
            .order("created_at", desc=True)
            .limit(AUDIT_FEEDBACK_LIMIT)
        )
        if doc_type and doc_type in AUDIT_DOC_TYPES:
            query = query.eq("doc_type", doc_type)

        jobs = query.execute().data or []
        job_ids = [row.get("job_id") for row in jobs if row.get("job_id")]
        if not job_ids:
            return feedback

        review_rows = sb.table("audit_reviews").select("job_id,status,comment,updated_at").in_("job_id", job_ids).execute().data or []
        if not review_rows:
            return feedback

        history_map = {r.get("job_id"): r for r in (history_records or []) if r.get("job_id")}
        missing_ids = [j for j in job_ids if j not in history_map]
        if missing_ids:
            result_rows = sb.table("audit_results").select("job_id,result_json").in_("job_id", missing_ids).execute().data or []
            for row in result_rows:
                result_json = row.get("result_json") or {}
                history_map[row.get("job_id")] = {
                    "job_id": row.get("job_id"),
                    "risk_level": result_json.get("risk_level"),
                    "findings": result_json.get("findings") if isinstance(result_json.get("findings"), list) else [],
                    "result": result_json,
                }

        fp_counter: Counter = Counter()
        fn_counter: Counter = Counter()
        notes: List[str] = []
        for row in review_rows:
            status = _safe_text(row.get("status")).lower()
            if status not in {"approved", "rejected", "need_more"}:
                continue
            feedback["reviewed_count"] += 1
            feedback[f"{status}_count"] += 1

            comment = _safe_text(row.get("comment"))
            if comment:
                notes.append(comment)

            history = history_map.get(row.get("job_id")) or {}
            result = history.get("result") if isinstance(history, dict) else {}
            if not isinstance(result, dict):
                result = {}
            risk = _safe_text(result.get("risk_level")).lower()
            findings = result.get("findings") if isinstance(result.get("findings"), list) else []
            top_msg = _safe_text(findings[0].get("message")) if findings else "风险判断"

            if status == "approved" and risk in {"high", "medium"}:
                fp_counter[top_msg] += 1
            if status == "rejected" and risk == "low":
                fn_counter[top_msg] += 1

        feedback["false_positive_hints"] = [item for item, _ in fp_counter.most_common(3)]
        feedback["false_negative_hints"] = [item for item, _ in fn_counter.most_common(3)]
        feedback["review_notes"] = notes[:3]
        return feedback
    except Exception as e:
        print(f"[Audit Feedback] Load failed: {e}")
        return feedback


def _feedback_prompt(feedback_ctx: Dict[str, Any]) -> str:
    reviewed = int(feedback_ctx.get("reviewed_count") or 0)
    if reviewed <= 0:
        return "暂无人工复核反馈数据。"
    lines = [
        f"最近人工复核样本: {reviewed}",
        f"通过: {feedback_ctx.get('approved_count', 0)}，驳回: {feedback_ctx.get('rejected_count', 0)}，补件: {feedback_ctx.get('need_more_count', 0)}",
    ]
    if feedback_ctx.get("false_positive_hints"):
        lines.append(f"高频疑似误报点: {feedback_ctx['false_positive_hints']}")
    if feedback_ctx.get("false_negative_hints"):
        lines.append(f"高频疑似漏报点: {feedback_ctx['false_negative_hints']}")
    if feedback_ctx.get("review_notes"):
        lines.append(f"复核备注样例: {feedback_ctx['review_notes']}")
    return "\n".join(lines)


def _truncate_text(text: str, limit: int = AI_MAX_TEXT_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _normalize_severity(value: Any, default: str = "medium") -> str:
    text = str(value or "").lower()
    if "high" in text or "critical" in text:
        return "high"
    if "low" in text or "minor" in text:
        return "low"
    if "medium" in text or "moderate" in text:
        return "medium"
    if text in {"h", "m", "l"}:
        return {"h": "high", "m": "medium", "l": "low"}[text]
    return default


def _normalize_risk_level(value: Any, default: str = "medium") -> str:
    return _normalize_severity(value, default=default)


def _coerce_ai_assessment(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        parsed = AuditAIAssessment.model_validate(payload)
    except ValidationError:
        return {}
    data = parsed.model_dump(by_alias=True, exclude_none=True)
    data["risk_level"] = _normalize_risk_level(data.get("risk_level"))
    if "pass" not in data:
        data["pass"] = data["risk_level"] == "low"

    findings: List[Dict[str, Any]] = []
    for item in data.get("findings", []) or []:
        if isinstance(item, AuditAIFinding):
            item = item.model_dump(exclude_none=True)
        if not isinstance(item, dict):
            continue
        message = item.get("message") or item.get("issue") or item.get("problem")
        if not message:
            continue
        reason = _safe_text(item.get("reason") or message)
        suggestion = _safe_text(item.get("suggestion") or "建议人工复核")
        confidence = item.get("confidence")
        if confidence is None:
            confidence = data.get("confidence")
        evidence = item.get("evidence")
        if evidence and not isinstance(evidence, dict):
            evidence = {"text": _safe_text(evidence), "highlight": _safe_text(evidence)}
        findings.append(
            _build_finding(
                source="ai",
                decision_mode="ai_semantic",
                finding_type=_safe_text(item.get("type") or "semantic"),
                severity=item.get("severity") or "medium",
                message=_safe_text(message),
                reason=reason,
                suggestion=suggestion,
                action=_safe_text(item.get("action") or suggestion),
                evidence=evidence,
                confidence=confidence if confidence is not None else 0.72,
            )
        )

    data["findings"] = findings[:AI_MAX_FINDINGS]
    if "confidence" in data:
        data["confidence"] = _clamp(_safe_float(data["confidence"]) or 0.72, 0.0, 1.0)
    return data


def _run_ai_review(
    doc_type: str,
    fields: Dict[str, Any],
    raw_text: str,
    rule_findings: List[Dict[str, Any]],
    high_risk_rule: bool,
    model_type: str,
    erp_ctx: Dict[str, Any],
    feedback_ctx: Dict[str, Any],
    anomaly_stats: Dict[str, Any],
) -> Dict[str, Any]:
    if not ask_llm:
        return {}

    rule_signals = [
        {
            "rule_id": f.get("rule_id"),
            "severity": f.get("severity"),
            "message": f.get("message"),
            "reason": f.get("reason"),
            "suggestion": f.get("suggestion"),
            "confidence": f.get("confidence"),
            "source": f.get("source"),
        }
        for f in (rule_findings or [])
    ][:AI_MAX_FINDINGS]

    erp_digest = {
        "provider": erp_ctx.get("provider"),
        "contract_amount": erp_ctx.get("contract_amount"),
        "po_amount": erp_ctx.get("po_amount"),
        "paid_amount": erp_ctx.get("paid_amount"),
        "budget_remaining": erp_ctx.get("budget_remaining"),
        "vendor_status": erp_ctx.get("vendor_status"),
        "blacklist_hit": erp_ctx.get("blacklist_hit"),
    }

    prompt = f"""
你是一名资深的智能审单/风控审计专家。规则结果仅供参考，AI 判断为主。
文档类型: {doc_type}
是否触发高风险规则: {high_risk_rule}

抽取字段 (json):
{json.dumps(fields, ensure_ascii=False)}

规则信号 (json):
{json.dumps(rule_signals, ensure_ascii=False)}

ERP上下文 (json):
{json.dumps(erp_digest, ensure_ascii=False)}

异常统计 (json):
{json.dumps(anomaly_stats or {}, ensure_ascii=False)}

人工复核反馈:
{_feedback_prompt(feedback_ctx)}

OCR 原文节选:
{_truncate_text(raw_text)}

如果触发高风险规则为 true，则必须保持 risk_level="high" 且 pass=false，并在 summary 中说明原因。
否则请综合语义和跨字段一致性等风险进行判断。

请只返回严格 JSON，不要输出 Markdown 或额外文本。
注意：summary、findings.message、findings.suggestion、evidence.text、evidence.highlight 等所有自然语言内容必须用中文（简洁、专业）。

返回 JSON 结构:
{{
  "risk_level": "low|medium|high",
  "pass": true/false,
  "summary": "简短说明",
  "findings": [
    {{"type": "semantic|cross_doc|policy|anomaly", "severity": "low|medium|high", "message": "...", "reason": "...", "suggestion": "...", "action":"...", "confidence": 0.0, "decision_mode":"ai_semantic", "evidence": {{"text": "...", "highlight": "..."}}}}
  ],
  "confidence": 0.0
}}
""".strip()

    response = ask_llm(prompt, model_type=model_type)
    payload = _extract_json_payload(response)
    if not payload:
        return {}
    assessment = _coerce_ai_assessment(payload)
    if not assessment:
        return {}
    if high_risk_rule:
        assessment["risk_level"] = "high"
        assessment["pass"] = False
    return assessment


def _run_cross_document_checks(
    doc_type: str,
    fields: Dict[str, Any],
    erp_ctx: Dict[str, Any],
    history_records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    amount = _safe_float(fields.get("total_amount"))
    contract_no = _safe_text(fields.get("contract_no"))
    invoice_no = _safe_text(fields.get("invoice_no"))
    vendor = _safe_text(fields.get("vendor") or fields.get("payee"))
    contract_date = _parse_date(fields.get("contract_date"))
    invoice_date = _parse_date(fields.get("invoice_date"))
    payment_date = _parse_date(fields.get("payment_date"))

    contract_amount = _safe_float(erp_ctx.get("contract_amount"))
    po_amount = _safe_float(erp_ctx.get("po_amount"))
    paid_amount = _safe_float(erp_ctx.get("paid_amount")) or 0.0
    budget_remaining = _safe_float(erp_ctx.get("budget_remaining"))
    expected_vendor = _safe_text(erp_ctx.get("expected_vendor"))
    vendor_status = _safe_text(erp_ctx.get("vendor_status")).lower()
    blacklist_hit = _safe_bool(erp_ctx.get("blacklist_hit"))

    same_contract_records = []
    if contract_no:
        same_contract_records = [
            rec for rec in history_records
            if _safe_text((rec.get("fields") or {}).get("contract_no")) == contract_no
        ]
    history_paid_amount = 0.0
    for rec in same_contract_records:
        rec_doc_type = _safe_text(rec.get("doc_type")).lower()
        if rec_doc_type not in {"payment", "expense"}:
            continue
        rec_amount = _safe_float((rec.get("fields") or {}).get("total_amount"))
        if rec_amount is not None:
            history_paid_amount += rec_amount
    if _safe_float(erp_ctx.get("history_paid_amount")) is None:
        erp_ctx["history_paid_amount"] = history_paid_amount
    if paid_amount <= 0 and history_paid_amount > 0:
        paid_amount = history_paid_amount

    def _add_check(
        check_id: str,
        name: str,
        passed: bool,
        reason: str,
        severity: str = "medium",
        suggestion: str = "建议人工复核",
        confidence: float = 0.95,
        actual: Any = None,
        expected: Any = None,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "name": name,
                "passed": bool(passed),
                "severity": _normalize_severity("low" if passed else severity),
                "reason": reason,
                "actual": actual,
                "expected": expected,
            }
        )
        if passed:
            return
        findings.append(
            _build_finding(
                source="cross_doc",
                decision_mode="cross_doc_reconciliation",
                finding_type=check_id,
                severity=severity,
                message=name,
                reason=reason,
                suggestion=suggestion,
                action=suggestion,
                evidence=evidence,
                confidence=confidence,
            )
        )

    _add_check(
        "vendor_blacklist",
        "供应商黑名单校验",
        not blacklist_hit,
        "供应商命中ERP黑名单" if blacklist_hit else "供应商未命中黑名单",
        severity="high",
        suggestion="建议驳回并触发人工复核",
        confidence=0.99,
        actual=vendor or None,
        expected="不在黑名单",
        evidence={"text": vendor, "highlight": vendor} if vendor else None,
    )

    blocked_status = {"blacklisted", "blocked", "high_risk", "freeze"}
    if vendor_status:
        _add_check(
            "vendor_status",
            "供应商状态校验",
            vendor_status not in blocked_status,
            f"供应商状态为 {vendor_status}",
            severity="high" if vendor_status in blocked_status else "low",
            suggestion="建议人工复核供应商资质",
            confidence=0.97,
            actual=vendor_status,
            expected="normal/active",
        )

    if amount is not None and contract_amount is not None:
        _add_check(
            "contract_amount_limit",
            "金额不超过合同额度",
            amount <= contract_amount,
            f"单据金额 {amount:.2f}，合同额度 {contract_amount:.2f}",
            severity="high",
            suggestion="建议核对合同金额或补充审批",
            actual=amount,
            expected=contract_amount,
            evidence={"text": str(amount), "highlight": str(amount)},
        )

    if amount is not None and po_amount is not None:
        _add_check(
            "po_amount_limit",
            "金额不超过PO额度",
            amount <= po_amount,
            f"单据金额 {amount:.2f}，PO额度 {po_amount:.2f}",
            severity="medium",
            suggestion="建议核对采购订单额度",
            actual=amount,
            expected=po_amount,
        )

    if amount is not None and contract_amount is not None:
        projected = paid_amount + amount if doc_type in {"payment", "expense"} else paid_amount
        _add_check(
            "paid_projection_limit",
            "累计支付不超过合同额度",
            projected <= contract_amount,
            f"已付 {paid_amount:.2f}，本次 {amount:.2f}，预计累计 {projected:.2f}，合同额度 {contract_amount:.2f}",
            severity="high",
            suggestion="建议驳回或拆分付款，避免超付",
            actual=projected,
            expected=contract_amount,
        )

    if amount is not None and budget_remaining is not None:
        _add_check(
            "budget_remaining",
            "预算余额校验",
            amount <= budget_remaining,
            f"本次金额 {amount:.2f}，预算剩余 {budget_remaining:.2f}",
            severity="high",
            suggestion="建议补充预算审批或驳回",
            actual=amount,
            expected=budget_remaining,
        )

    if vendor and expected_vendor:
        _add_check(
            "vendor_consistency",
            "主体一致性校验",
            vendor == expected_vendor,
            f"单据主体 {vendor}，ERP主体 {expected_vendor}",
            severity="medium",
            suggestion="建议核对合同主体与收款方一致性",
            actual=vendor,
            expected=expected_vendor,
        )

    if invoice_no:
        history_dup = [
            rec for rec in history_records
            if _safe_text((rec.get("fields") or {}).get("invoice_no")) == invoice_no
        ]
        has_dup = _safe_bool(erp_ctx.get("invoice_exists")) or len(history_dup) > 0
        _add_check(
            "invoice_duplicate",
            "发票号重复校验",
            not has_dup,
            f"发票号 {invoice_no} 在ERP/历史记录中已存在" if has_dup else f"发票号 {invoice_no} 未发现重复",
            severity="high",
            suggestion="建议驳回并核查是否重复报销",
            confidence=0.99 if has_dup else 0.92,
            actual=invoice_no,
            expected="唯一",
            evidence={"text": invoice_no, "highlight": invoice_no},
        )

    if doc_type in {"payment", "expense"}:
        has_ref = bool(contract_no or invoice_no)
        _add_check(
            "reference_required",
            "单据关联编号校验",
            has_ref,
            "付款/报销缺少合同号或发票号" if not has_ref else "存在合同号或发票号",
            severity="medium",
            suggestion="建议补充合同号或发票号",
            actual={"contract_no": contract_no or None, "invoice_no": invoice_no or None},
            expected="至少一个关联编号",
        )

    if contract_date and invoice_date:
        _add_check(
            "contract_invoice_date",
            "合同与发票日期顺序",
            invoice_date >= contract_date,
            f"合同日期 {contract_date.date()}，发票日期 {invoice_date.date()}",
            severity="medium",
            suggestion="建议核对合同签署与开票时间",
            actual=invoice_date.date().isoformat(),
            expected=f">={contract_date.date().isoformat()}",
        )

    if invoice_date and payment_date:
        _add_check(
            "invoice_payment_date",
            "发票与付款日期顺序",
            payment_date >= invoice_date,
            f"发票日期 {invoice_date.date()}，付款日期 {payment_date.date()}",
            severity="medium",
            suggestion="建议核对付款时间与票据时间",
            actual=payment_date.date().isoformat(),
            expected=f">={invoice_date.date().isoformat()}",
        )

    return findings, checks


def _run_anomaly_detection(
    doc_type: str,
    fields: Dict[str, Any],
    history_records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}

    amount = _safe_float(fields.get("total_amount"))
    if amount is None:
        return findings, stats

    vendor = _safe_text(fields.get("vendor") or fields.get("payee"))
    reimburser = _safe_text(fields.get("reimburser"))
    invoice_no = _safe_text(fields.get("invoice_no"))
    current_date = _parse_date(fields.get("payment_date") or fields.get("invoice_date") or fields.get("contract_date")) or datetime.utcnow()

    def _amounts(filter_fn) -> List[float]:
        vals = []
        for rec in history_records:
            if not filter_fn(rec):
                continue
            rec_amount = _safe_float((rec.get("fields") or {}).get("total_amount"))
            if rec_amount is not None:
                vals.append(rec_amount)
        return vals

    def _detect_zscore(group_name: str, values: List[float], severity_base: str = "medium") -> None:
        if len(values) < ANOMALY_MIN_SAMPLES:
            return
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
        std = variance ** 0.5
        if std <= 0.001:
            return
        zscore = (amount - mean) / std
        stats[f"{group_name}_zscore"] = round(zscore, 4)
        stats[f"{group_name}_mean"] = round(mean, 4)
        stats[f"{group_name}_std"] = round(std, 4)
        stats[f"{group_name}_samples"] = len(values)
        if abs(zscore) < 2.5:
            return
        severity = "high" if abs(zscore) >= 3.5 else severity_base
        confidence = _clamp(0.7 + min(abs(zscore), 6.0) / 10.0, 0.7, 0.99)
        findings.append(
            _build_finding(
                source="anomaly",
                decision_mode="anomaly_detection",
                finding_type=f"{group_name}_amount_anomaly",
                severity=severity,
                message=f"{group_name}金额异常",
                reason=f"当前金额 {amount:.2f} 与历史均值 {mean:.2f} 偏差显著（z={zscore:.2f}）",
                suggestion="建议人工复核交易合理性与业务背景",
                action="建议人工复核",
                evidence={"text": f"金额 {amount:.2f}，均值 {mean:.2f}，标准差 {std:.2f}", "highlight": f"z={zscore:.2f}"},
                confidence=confidence,
            )
        )

    same_vendor_amounts = _amounts(
        lambda rec: _safe_text((rec.get("fields") or {}).get("vendor") or (rec.get("fields") or {}).get("payee")) == vendor if vendor else False
    )
    same_reimburser_amounts = _amounts(
        lambda rec: _safe_text((rec.get("fields") or {}).get("reimburser")) == reimburser if reimburser else False
    )
    same_category_amounts = _amounts(lambda rec: _safe_text(rec.get("doc_type")).lower() == doc_type)

    _detect_zscore("同供应商", same_vendor_amounts, severity_base="medium")
    _detect_zscore("同报销人", same_reimburser_amounts, severity_base="medium")
    _detect_zscore("同品类", same_category_amounts, severity_base="low")

    if invoice_no:
        duplicate_invoice = [
            rec for rec in history_records
            if _safe_text((rec.get("fields") or {}).get("invoice_no")) == invoice_no
        ]
        if duplicate_invoice:
            findings.append(
                _build_finding(
                    source="anomaly",
                    decision_mode="anomaly_detection",
                    finding_type="duplicate_invoice",
                    severity="high",
                    message="疑似重复报销",
                    reason=f"发票号 {invoice_no} 在历史审单中已出现 {len(duplicate_invoice)} 次",
                    suggestion="建议驳回并核查原始报销记录",
                    action="建议驳回",
                    evidence={"text": invoice_no, "highlight": invoice_no},
                    confidence=0.99,
                )
            )

    duplicate_reimbursement_count = 0
    for rec in history_records:
        rec_fields = rec.get("fields") or {}
        rec_reimburser = _safe_text(rec_fields.get("reimburser"))
        rec_amount = _safe_float(rec_fields.get("total_amount"))
        if not reimburser or rec_reimburser != reimburser or rec_amount is None:
            continue
        if abs(rec_amount - amount) > 0.01:
            continue
        rec_date = _parse_date(rec_fields.get("payment_date") or rec_fields.get("invoice_date") or rec.get("created_at"))
        if not rec_date:
            continue
        if abs((current_date - rec_date).days) <= 45:
            duplicate_reimbursement_count += 1

    if duplicate_reimbursement_count > 0:
        findings.append(
            _build_finding(
                source="anomaly",
                decision_mode="anomaly_detection",
                finding_type="duplicate_reimbursement_window",
                severity="high",
                message="短周期重复报销风险",
                reason=f"报销人 {reimburser or '未知'} 在45天内出现相同金额报销 {duplicate_reimbursement_count} 次",
                suggestion="建议核查是否重复提交并走人工复核",
                action="建议驳回",
                evidence={"text": f"{reimburser} / {amount:.2f}", "highlight": f"{amount:.2f}"},
                confidence=0.98,
            )
        )

    stats["duplicate_reimbursement_count"] = duplicate_reimbursement_count
    return findings, stats


def _has_high_risk(findings: List[Dict[str, Any]]) -> bool:
    return any(_normalize_severity(f.get("severity"), default="low") == "high" for f in findings)


def _risk_level(findings: List[Dict[str, Any]]) -> str:
    severities = [_normalize_severity(f.get("severity"), default="low") for f in findings]
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _build_summary(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "未发现明显问题，建议通过。"
    high = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")
    medium = sum(1 for f in findings if str(f.get("severity", "")).lower() == "medium")
    low = sum(1 for f in findings if str(f.get("severity", "")).lower() == "low")
    return f"共发现 {len(findings)} 项问题，高风险 {high} 项，中风险 {medium} 项，低风险 {low} 项。"


def _build_finding_breakdown(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_source = Counter(_safe_text(f.get("source") or "unknown") for f in findings)
    by_severity = Counter(_safe_text(f.get("severity") or "unknown") for f in findings)
    return {
        "total": len(findings),
        "by_source": dict(by_source),
        "by_severity": dict(by_severity),
    }


def _compute_audit_score(
    findings: List[Dict[str, Any]],
    ai_assessment: Optional[Dict[str, Any]],
    erp_ctx: Dict[str, Any],
) -> float:
    score = 100.0
    for item in findings:
        severity = _normalize_severity(item.get("severity"), default="low")
        weight = float(RISK_WEIGHT.get(severity, 5))
        source = _safe_text(item.get("source"))
        if source == "ai":
            weight *= 0.85
        elif source == "anomaly":
            weight *= 1.1
        confidence = _safe_float(item.get("confidence"))
        if confidence is not None:
            weight *= _clamp(0.75 + confidence * 0.4, 0.6, 1.2)
        score -= weight

    if _safe_bool(erp_ctx.get("blacklist_hit")):
        score -= 12

    if not findings:
        score += 3

    ai_conf = _safe_float((ai_assessment or {}).get("confidence"))
    if ai_conf is not None:
        score *= _clamp(0.9 + (ai_conf - 0.5) * 0.25, 0.8, 1.05)

    return round(_clamp(score, 0.0, 100.0), 2)


def _build_decision_trace(
    *,
    doc_type: str,
    fields: Dict[str, Any],
    rule_findings: List[Dict[str, Any]],
    cross_findings: List[Dict[str, Any]],
    anomaly_findings: List[Dict[str, Any]],
    ai_assessment: Dict[str, Any],
    erp_ctx: Dict[str, Any],
    feedback_ctx: Dict[str, Any],
    risk_level: str,
    is_pass: bool,
) -> List[Dict[str, Any]]:
    return [
        {
            "step": "extract_fields",
            "detail": "完成OCR与字段抽取",
            "doc_type": doc_type,
            "fields_count": len(fields.keys()),
            "at": _now_iso(),
        },
        {
            "step": "rule_engine",
            "detail": "规则引擎检测完成",
            "hits": len(rule_findings),
            "high_risk_hits": sum(1 for f in rule_findings if _normalize_severity(f.get("severity")) == "high"),
            "at": _now_iso(),
        },
        {
            "step": "cross_doc_reconciliation",
            "detail": "跨单据与ERP对账完成",
            "hits": len(cross_findings),
            "erp_provider": erp_ctx.get("provider"),
            "at": _now_iso(),
        },
        {
            "step": "anomaly_detection",
            "detail": "历史异常检测完成",
            "hits": len(anomaly_findings),
            "at": _now_iso(),
        },
        {
            "step": "ai_semantic_review",
            "detail": "AI语义审单完成",
            "risk_level": (ai_assessment or {}).get("risk_level"),
            "confidence": (ai_assessment or {}).get("confidence"),
            "feedback_reviewed": feedback_ctx.get("reviewed_count", 0),
            "at": _now_iso(),
        },
        {
            "step": "final_decision",
            "detail": "生成最终结论",
            "risk_level": risk_level,
            "pass": is_pass,
            "at": _now_iso(),
        },
    ]


def _fetch_erp_context(
    fields: Dict[str, Any],
    user_id: str,
    doc_type: str,
    history_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    history_records = history_records or []
    context = {
        "provider": ERP_PROVIDER,
        "contract_amount": None,
        "po_amount": None,
        "paid_amount": None,
        "budget_remaining": None,
        "vendor_status": "unknown",
        "blacklist_hit": False,
        "expected_vendor": None,
        "invoice_exists": False,
        "existing_invoice_nos": [],
        "history_paid_amount": 0.0,
        "supported_providers": get_supported_erp_providers() if callable(get_supported_erp_providers) else [ERP_PROVIDER],
    }

    if callable(get_erp_adapter):
        try:
            adapter = get_erp_adapter(ERP_PROVIDER, user_id=user_id)
            adapter_ctx = adapter.fetch_context(fields) or {}
            if isinstance(adapter_ctx, dict):
                context.update(adapter_ctx)
                context["provider"] = adapter_ctx.get("provider") or context["provider"]
        except Exception as e:
            print(f"[Audit ERP] Adapter fetch failed: {e}")

    contract_no = _safe_text(fields.get("contract_no"))
    invoice_no = _safe_text(fields.get("invoice_no"))
    same_contract = []
    if contract_no:
        same_contract = [
            rec for rec in history_records
            if _safe_text((rec.get("fields") or {}).get("contract_no")) == contract_no
        ]
    history_paid = 0.0
    for rec in same_contract:
        rec_type = _safe_text(rec.get("doc_type")).lower()
        if rec_type not in {"payment", "expense"}:
            continue
        rec_amount = _safe_float((rec.get("fields") or {}).get("total_amount"))
        if rec_amount is not None:
            history_paid += rec_amount
    context["history_paid_amount"] = round(history_paid, 4)

    if context.get("paid_amount") is None and history_paid > 0:
        context["paid_amount"] = history_paid

    if context.get("contract_amount") is None and same_contract:
        contract_amounts = [
            _safe_float((rec.get("fields") or {}).get("total_amount"))
            for rec in same_contract
            if _safe_text(rec.get("doc_type")).lower() == "contract"
        ]
        contract_amounts = [v for v in contract_amounts if v is not None]
        if contract_amounts:
            context["contract_amount"] = max(contract_amounts)

    if context.get("expected_vendor") in (None, "") and same_contract:
        for rec in same_contract:
            vendor = _safe_text((rec.get("fields") or {}).get("vendor") or (rec.get("fields") or {}).get("payee"))
            if vendor:
                context["expected_vendor"] = vendor
                break

    if invoice_no and not context.get("invoice_exists"):
        history_dup = [
            rec for rec in history_records
            if _safe_text((rec.get("fields") or {}).get("invoice_no")) == invoice_no
        ]
        if history_dup:
            context["invoice_exists"] = True
            context["existing_invoice_nos"] = [invoice_no]

    context["doc_type"] = doc_type
    return context


def _persist_audit_result(job_id: str, result: Dict[str, Any]) -> None:
    if not require_supabase:
        return
    now = _now_iso()
    try:
        sb = require_supabase()
        sb.table("audit_results").upsert(
            {
                "job_id": job_id,
                "result_json": result,
                "updated_at": now,
                "created_at": now,
            },
            on_conflict="job_id",
        ).execute()
        return
    except Exception:
        pass
    try:
        sb = require_supabase()
        sb.table("audit_results").update({"result_json": result, "updated_at": now}).eq("job_id", job_id).execute()
    except Exception:
        try:
            sb = require_supabase()
            sb.table("audit_results").insert({"job_id": job_id, "result_json": result, "created_at": now}).execute()
        except Exception as e:
            print(f"[Audit Result] Persist failed: {e}")


def _update_job_result_in_memory(job_id: str, result: Dict[str, Any]) -> None:
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            return
        job["result"] = result
        job["updated_at"] = _now_iso()


def push_audit_action_to_erp(
    job_id: str,
    action: str,
    operator_id: str,
    comment: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    action_norm = _safe_text(action).lower()
    if action_norm not in ERP_ACTIONS:
        return False, {"error": "Invalid action, expected approved/rejected/need_more"}
    snapshot = get_job_snapshot(job_id)
    if not snapshot:
        return False, {"error": "Job not found"}
    if _safe_text(snapshot.get("status")) != "done":
        return False, {"error": "Job is not completed"}
    result = snapshot.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    user_id = _safe_text(snapshot.get("user_id")) or "anonymous"
    if not callable(get_erp_adapter):
        return False, {"error": "ERP adapter unavailable"}
    try:
        adapter = get_erp_adapter(ERP_PROVIDER, user_id=user_id)
        sync_payload = adapter.writeback_audit_action(
            job_id=job_id,
            action=action_norm,
            operator_id=operator_id or "system",
            result=result,
            comment=comment,
        )
    except Exception as e:
        return False, {"error": f"ERP writeback failed: {e}"}

    erp_action = {
        "action": action_norm,
        "operator_id": operator_id or "system",
        "comment": comment,
        "trace_id": sync_payload.get("trace_id"),
        "provider": sync_payload.get("provider"),
        "status": sync_payload.get("status"),
        "stored": sync_payload.get("stored"),
        "at": _now_iso(),
    }
    result["erp_action"] = erp_action
    result["erp_trace_id"] = sync_payload.get("trace_id")
    result["erp_sync_status"] = sync_payload.get("status")
    decision_trace = result.get("decision_trace") if isinstance(result.get("decision_trace"), list) else []
    decision_trace.append(
        {
            "step": "erp_writeback",
            "detail": "审单结论已回写ERP",
            "action": action_norm,
            "trace_id": sync_payload.get("trace_id"),
            "provider": sync_payload.get("provider"),
            "status": sync_payload.get("status"),
            "at": _now_iso(),
        }
    )
    result["decision_trace"] = decision_trace

    _persist_audit_result(job_id, result)
    _update_job_result_in_memory(job_id, result)
    _update_db("audit_jobs", {"updated_at": _now_iso()}, job_id)
    return True, {"job_id": job_id, "erp_action": erp_action, "result": result}


def _parse_with_loader(file_bytes: bytes, filename: str) -> Tuple[str, List[str]]:
    if not load_documents:
        return "", []
    docs = load_documents(file_bytes, filename) or []
    page_texts = []
    for doc in docs:
        text = (doc.page_content or "").strip()
        if text:
            page_texts.append(text)
    raw_text = "\n\n".join(page_texts).strip()
    return raw_text, page_texts


def _parse_with_ocr(file_bytes: bytes, filename: str) -> Tuple[str, List[str], Optional[float]]:
    engine = _get_ocr_engine()
    if not engine:
        raise RuntimeError("OCR engine unavailable")
    result = engine.recognize(file_bytes, filename)
    raw_text = (result.get("text") or "").strip()
    meta = result.get("meta") or {}

    confidence = None
    scores: List[float] = []
    for page in meta.get("pages_blocks", []) or []:
        for row in page.get("rows", []) or []:
            for line in row.get("lines", []) or []:
                score = line.get("score")
                if isinstance(score, (int, float)):
                    scores.append(score)
    if scores:
        confidence = sum(scores) / len(scores)

    return raw_text, [], confidence


def _extract_text(file_bytes: bytes, filename: str) -> Tuple[str, List[str], Optional[float]]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        return _parse_with_ocr(file_bytes, filename)

    if ext == ".pdf":
        raw_text, page_texts = _parse_with_loader(file_bytes, filename)
        if len(raw_text) < 40:
            return _parse_with_ocr(file_bytes, filename)
        return raw_text, page_texts, None

    if ext in {".doc", ".docx", ".txt"}:
        raw_text, page_texts = _parse_with_loader(file_bytes, filename)
        return raw_text, page_texts, None

    try:
        raw_text = file_bytes.decode("utf-8", errors="ignore").strip()
        return raw_text, [], None
    except Exception:
        return "", [], None


def run_audit_job_from_job_id(job_id: str) -> None:
    job = _load_job_from_db(job_id)
    if not job:
        raise RuntimeError(f"Audit job not found: {job_id}")

    file_url = job.get("file_url")
    if not file_url:
        raise RuntimeError(f"Audit job missing file path: {job_id}")

    local_path = os.path.join(BASE_DIR, "storage", str(file_url).replace("/", os.sep))
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Audit file not found: {local_path}")

    with open(local_path, "rb") as f:
        file_bytes = f.read()

    filename = job.get("file_name") or os.path.basename(local_path) or "document"
    user_id = job.get("user_id") or "anonymous"
    doc_type = job.get("doc_type") or "auto"
    run_audit_job(job_id, file_bytes, filename, user_id, doc_type)


def enqueue_audit_job(file_bytes: bytes, filename: str, user_id: str, doc_type: Optional[str]) -> Dict[str, Any]:
    if enqueue_job is None:
        raise RuntimeError("Audit queue is unavailable, check Redis/RQ dependencies")

    job = create_job(file_bytes, filename, user_id, doc_type)
    queue_job_id = f"audit:{job['job_id']}"

    try:
        enqueue_job(
            queue_name=AUDIT_QUEUE_NAME,
            func=run_audit_job_from_job_id,
            kwargs={"job_id": job["job_id"]},
            job_id=queue_job_id,
            retry_max=AUDIT_JOB_RETRY_MAX,
            timeout=AUDIT_JOB_TIMEOUT_SECONDS,
        )
    except Exception as e:
        update_job(
            job["job_id"],
            status="failed",
            stage="failed",
            progress=STAGE_PROGRESS["failed"],
            error_message=f"Queue enqueue failed: {e}",
        )
        raise

    return job


def run_audit_job(job_id: str, file_bytes: bytes, filename: str, user_id: str, doc_type: str) -> None:
    try:
        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return
        update_job(job_id, status="running", progress=10, stage="ocr")

        raw_text, page_texts, ocr_confidence = _extract_text(file_bytes, filename)
        _update_db("audit_docs", {
            "raw_text": raw_text,
            "page_texts": page_texts,
            "ocr_confidence": ocr_confidence,
        }, job_id, key="job_id")

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return

        effective_doc_type = doc_type
        if doc_type == "auto":
            llm_doc_type = _infer_doc_type_llm(raw_text) if AUDIT_LLM_ENABLED else None
            effective_doc_type = llm_doc_type or _infer_doc_type(raw_text)
            update_job(job_id, doc_type=effective_doc_type)
            _update_db("audit_docs", {"doc_type": effective_doc_type}, job_id, key="job_id")

        update_job(job_id, progress=STAGE_PROGRESS["ocr"], stage="extract")

        fields = _extract_fields(raw_text, effective_doc_type)
        fields = _validate_fields(fields)

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return

        history_records = _collect_history_records(user_id)
        feedback_ctx = _collect_review_feedback(user_id, effective_doc_type, history_records)
        erp_ctx = _fetch_erp_context(fields, user_id, effective_doc_type, history_records)

        update_job(job_id, progress=STAGE_PROGRESS["extract"], stage="rules")

        rule_findings = _run_rules(effective_doc_type, fields, raw_text, erp_ctx)
        cross_findings, erp_checks = _run_cross_document_checks(effective_doc_type, fields, erp_ctx, history_records)
        anomaly_findings, anomaly_stats = _run_anomaly_detection(effective_doc_type, fields, history_records)
        deterministic_findings = list(rule_findings) + list(cross_findings) + list(anomaly_findings)

        if deterministic_findings:
            rows = []
            for f in deterministic_findings:
                rows.append({
                    "job_id": job_id,
                    "rule_id": f.get("rule_id") or f.get("type"),
                    "severity": f.get("severity"),
                    "message": f.get("message"),
                    "suggestion": f.get("suggestion"),
                    "evidence": f.get("evidence"),
                    "created_at": _now_iso(),
                })
            _insert_db("audit_findings", rows)

        high_risk_gate = _has_high_risk(deterministic_findings)

        update_job(job_id, progress=STAGE_PROGRESS["rules"], stage="ai")
        ai_assessment = _run_ai_review(
            effective_doc_type,
            fields,
            raw_text,
            deterministic_findings,
            high_risk_gate,
            AUDIT_AI_BACKEND,
            erp_ctx,
            feedback_ctx,
            anomaly_stats,
        )

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return

        update_job(job_id, progress=STAGE_PROGRESS["ai"], stage="report")

        combined_findings = list(deterministic_findings)
        if ai_assessment and ai_assessment.get("findings"):
            combined_findings.extend(ai_assessment["findings"])

        if high_risk_gate:
            risk_level = "high"
            is_pass = False
            summary = (ai_assessment or {}).get("summary") or _build_summary(deterministic_findings)
        elif ai_assessment:
            risk_level = ai_assessment.get("risk_level") or _risk_level(deterministic_findings)
            is_pass = ai_assessment.get("pass") if "pass" in ai_assessment else risk_level == "low"
            summary = ai_assessment.get("summary") or _build_summary(combined_findings)
        else:
            risk_level = _risk_level(deterministic_findings)
            is_pass = risk_level == "low"
            summary = _build_summary(deterministic_findings)

        audit_score = _compute_audit_score(combined_findings, ai_assessment, erp_ctx)
        finding_breakdown = _build_finding_breakdown(combined_findings)
        decision_trace = _build_decision_trace(
            doc_type=effective_doc_type,
            fields=fields,
            rule_findings=rule_findings,
            cross_findings=cross_findings,
            anomaly_findings=anomaly_findings,
            ai_assessment=ai_assessment or {},
            erp_ctx=erp_ctx,
            feedback_ctx=feedback_ctx,
            risk_level=risk_level,
            is_pass=is_pass,
        )

        result = {
            "risk_level": risk_level,
            "pass": is_pass,
            "summary": summary,
            "findings": combined_findings,
            "extracted_fields": fields,
            "rule_findings": rule_findings,
            "cross_doc_findings": cross_findings,
            "anomaly_findings": anomaly_findings,
            "ai_assessment": ai_assessment or None,
            "erp_context": {
                "provider": erp_ctx.get("provider"),
                "contract_amount": erp_ctx.get("contract_amount"),
                "po_amount": erp_ctx.get("po_amount"),
                "paid_amount": erp_ctx.get("paid_amount"),
                "budget_remaining": erp_ctx.get("budget_remaining"),
                "vendor_status": erp_ctx.get("vendor_status"),
                "blacklist_hit": erp_ctx.get("blacklist_hit"),
                "expected_vendor": erp_ctx.get("expected_vendor"),
                "history_paid_amount": erp_ctx.get("history_paid_amount"),
            },
            "erp_checks": erp_checks,
            "anomaly_stats": anomaly_stats,
            "review_feedback": feedback_ctx,
            "finding_breakdown": finding_breakdown,
            "decision_trace": decision_trace,
            "audit_score": audit_score,
            "erp_action": None,
            "erp_trace_id": None,
        }

        _persist_audit_result(job_id, result)

        update_job(job_id, status="done", progress=STAGE_PROGRESS["done"], stage="done", result=result)

    except Exception as e:
        update_job(job_id, status="failed", progress=STAGE_PROGRESS["failed"], stage="failed", error_message=str(e))
        raise
