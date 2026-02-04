import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_STORAGE_ROOT = os.path.join(BASE_DIR, "storage", "audit")
RULES_DIR = os.path.join(BASE_DIR, "rules")
AI_MAX_TEXT_CHARS = 4000
AI_MAX_FINDINGS = 6
AUDIT_AI_BACKEND = os.getenv("AUDIT_AI_BACKEND", "local")
AUDIT_LLM_ENABLED = os.getenv("AUDIT_LLM_ENABLED", "true").lower() != "false"
AUDIT_LLM_BACKEND = os.getenv("AUDIT_LLM_BACKEND", AUDIT_AI_BACKEND)
AUDIT_LLM_MAX_CHARS = int(os.getenv("AUDIT_LLM_MAX_CHARS", "6000"))

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
EXECUTOR = ThreadPoolExecutor(max_workers=4)
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
    suggestion: Optional[str] = None
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
            "file_url": job.get("file_url"),
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
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = _now_iso()

    payload = {k: v for k, v in updates.items() if k != "result"}
    if payload:
        payload["updated_at"] = _now_iso()
        _update_db("audit_jobs", payload, job_id)


def _is_cancelled(job_id: str) -> bool:
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        return bool(job and job.get("cancelled"))


def cancel_audit_job(job_id: str) -> bool:
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            return False
        job["cancelled"] = True
        job["status"] = "cancelled"
        job["stage"] = "cancelled"
        job["progress"] = 100
        job["updated_at"] = _now_iso()
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
    file_name = job.get("file_name") or "document"
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
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if job:
            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "progress": job.get("progress", 0),
                "stage": job.get("stage"),
                "error_message": job.get("error_message"),
                "result": job.get("result"),
                "doc_type": job.get("doc_type"),
                "file_url": job.get("file_url"),
            }
    return _load_job_from_db(job_id)


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
            findings.append({
                "rule_id": rule.get("id"),
                "severity": rule.get("severity", "medium"),
                "message": rule.get("message", "规则触发"),
                "suggestion": rule.get("suggestion", ""),
                "evidence": _build_evidence(rule, ctx),
                "source": "rule",
            })
    return findings


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
        findings.append({
            "type": item.get("type") or "ai",
            "severity": _normalize_severity(item.get("severity")),
            "message": message,
            "suggestion": item.get("suggestion", ""),
            "evidence": item.get("evidence"),
            "source": "ai",
        })

    data["findings"] = findings[:AI_MAX_FINDINGS]
    return data


def _run_ai_review(
    doc_type: str,
    fields: Dict[str, Any],
    raw_text: str,
    rule_findings: List[Dict[str, Any]],
    high_risk_rule: bool,
    model_type: str,
) -> Dict[str, Any]:
    if not ask_llm:
        return {}

    rule_signals = [
        {
            "rule_id": f.get("rule_id"),
            "severity": f.get("severity"),
            "message": f.get("message"),
            "suggestion": f.get("suggestion"),
        }
        for f in (rule_findings or [])
    ][:AI_MAX_FINDINGS]

    prompt = f"""
你是一名资深的智能审单/风控审计专家。规则结果仅供参考，AI 判断为主。
文档类型: {doc_type}
是否触发高风险规则: {high_risk_rule}

抽取字段 (json):
{json.dumps(fields, ensure_ascii=False)}

规则信号 (json):
{json.dumps(rule_signals, ensure_ascii=False)}

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
    {{"type": "semantic|cross_doc|policy|anomaly", "severity": "low|medium|high", "message": "...", "suggestion": "...", "evidence": {{"text": "...", "highlight": "..."}}}}
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


def _fetch_erp_context(fields: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    return {}


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


def enqueue_audit_job(file_bytes: bytes, filename: str, user_id: str, doc_type: Optional[str]) -> Dict[str, Any]:
    job = create_job(file_bytes, filename, user_id, doc_type)
    EXECUTOR.submit(run_audit_job, job["job_id"], file_bytes, filename, user_id, job["doc_type"])
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

        erp_ctx = _fetch_erp_context(fields, user_id)

        update_job(job_id, progress=STAGE_PROGRESS["extract"], stage="rules")

        rule_findings = _run_rules(effective_doc_type, fields, raw_text, erp_ctx)
        if rule_findings:
            rows = []
            for f in rule_findings:
                rows.append({
                    "job_id": job_id,
                    "rule_id": f.get("rule_id"),
                    "severity": f.get("severity"),
                    "message": f.get("message"),
                    "suggestion": f.get("suggestion"),
                    "evidence": f.get("evidence"),
                    "created_at": _now_iso(),
                })
            _insert_db("audit_findings", rows)

        high_risk_rule = _has_high_risk(rule_findings)

        update_job(job_id, progress=STAGE_PROGRESS["rules"], stage="ai")
        ai_assessment = _run_ai_review(
            effective_doc_type,
            fields,
            raw_text,
            rule_findings,
            high_risk_rule,
            AUDIT_AI_BACKEND,
        )

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return

        update_job(job_id, progress=STAGE_PROGRESS["ai"], stage="report")

        combined_findings = list(rule_findings)
        if ai_assessment and ai_assessment.get("findings"):
            combined_findings.extend(ai_assessment["findings"])

        if high_risk_rule:
            risk_level = "high"
            is_pass = False
            summary = (ai_assessment or {}).get("summary") or _build_summary(rule_findings)
        elif ai_assessment:
            risk_level = ai_assessment.get("risk_level") or _risk_level(rule_findings)
            is_pass = ai_assessment.get("pass") if "pass" in ai_assessment else risk_level == "low"
            summary = ai_assessment.get("summary") or _build_summary(combined_findings)
        else:
            risk_level = _risk_level(rule_findings)
            is_pass = risk_level == "low"
            summary = _build_summary(rule_findings)

        result = {
            "risk_level": risk_level,
            "pass": is_pass,
            "summary": summary,
            "findings": combined_findings,
            "extracted_fields": fields,
            "rule_findings": rule_findings,
            "ai_assessment": ai_assessment or None,
        }

        _insert_db("audit_results", {
            "job_id": job_id,
            "result_json": result,
            "created_at": _now_iso(),
        })

        update_job(job_id, status="done", progress=STAGE_PROGRESS["done"], stage="done", result=result)

    except Exception as e:
        update_job(job_id, status="failed", progress=STAGE_PROGRESS["failed"], stage="failed", error_message=str(e))
