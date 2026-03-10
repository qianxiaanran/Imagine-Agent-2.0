import json
import os
import re
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, ValidationError, Field
from runtime_storage import RUNTIME_AUDIT_ROOT, ensure_runtime_layout, migrate_legacy_runtime_files

try:
    from ocr_manager import OCRManager, get_shared_ocr_manager
except Exception:
    OCRManager = None
    get_shared_ocr_manager = None

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
ensure_runtime_layout()
migrate_legacy_runtime_files()
LOCAL_STORAGE_ROOT = str(RUNTIME_AUDIT_ROOT)
AUDIT_STATE_ROOT = os.path.join(LOCAL_STORAGE_ROOT, "_state")
AUDIT_JOB_STATE_DIR = os.path.join(AUDIT_STATE_ROOT, "jobs")
AUDIT_CASE_STATE_DIR = os.path.join(AUDIT_STATE_ROOT, "cases")
AUDIT_ERP_QUEUE_STATE_DIR = os.path.join(AUDIT_STATE_ROOT, "erp_queue")
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
AUDIT_ERP_SYNC_MODE = os.getenv("AUDIT_ERP_SYNC_MODE", "queue").strip().lower() or "queue"
ERP_SYNC_MAX_RETRY = int(os.getenv("ERP_SYNC_MAX_RETRY", "3"))
ERP_ACTION_TABLES = ["audit_erp_actions", "erp_audit_actions"]
ERP_ACTIONS = {"approved", "rejected", "need_more"}
RISK_WEIGHT = {"high": 25, "medium": 12, "low": 5}
AUDIT_JOB_TIMEOUT_SECONDS = int(os.getenv("AUDIT_JOB_TIMEOUT_SECONDS", "5400"))
AUDIT_JOB_RETRY_MAX = int(os.getenv("AUDIT_JOB_RETRY_MAX", "2"))
AUDIT_INLINE_FALLBACK = os.getenv("AUDIT_INLINE_FALLBACK", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
AUDIT_SELF_ORG_NAMES = [
    str(item or "").strip()
    for item in os.getenv(
        "AUDIT_SELF_ORG_NAMES",
        "天津纺织集团进出口股份有限公司,TIANJIN TEXTILE GROUP IMPORT AND EXPORT INC.",
    ).split(",")
    if str(item or "").strip()
]

DOC_TYPE_ALIASES = {
    "auto": "auto",
    "trade_case": "trade_case",
    "invoice": "invoice",
    "contract": "contract",
    "payment": "payment",
    "expense": "expense",
    "import_declaration": "import_declaration",
    "export_declaration": "export_declaration",
    "packing_list": "packing_list",
    "bill_of_lading": "bill_of_lading",
    "air_waybill": "air_waybill",
    "certificate_of_origin": "certificate_of_origin",
    "\u81ea\u52a8\u8bc6\u522b": "auto",
    "\u8d38\u6613\u5355\u636e\u5305": "trade_case",
    "\u53d1\u7968": "invoice",
    "\u5408\u540c": "contract",
    "\u4ed8\u6b3e\u5355": "payment",
    "\u62a5\u9500\u5355": "expense",
    "\u62a5\u5173\u5355": "import_declaration",
    "\u88c5\u7bb1\u5355": "packing_list",
    "\u63d0\u5355": "bill_of_lading",
    "\u8fd0\u5355": "air_waybill",
    "\u539f\u4ea7\u5730\u8bc1": "certificate_of_origin",
}
DOC_TYPE_DISPLAY_NAMES = {
    "auto": "自动识别",
    "trade_case": "贸易单据包",
    "invoice": "发票",
    "contract": "合同",
    "payment": "付款单",
    "expense": "报销单",
    "import_declaration": "进口报关单",
    "export_declaration": "出口报关单",
    "packing_list": "装箱单",
    "bill_of_lading": "提单",
    "air_waybill": "空运运单",
    "certificate_of_origin": "原产地证",
}
DOC_SUBTYPE_DISPLAY_NAMES = {
    "trade_case_generic": "贸易单据包",
    "sales_contract": "销售合同",
    "purchase_contract": "采购合同",
    "sale_purchase_contract": "购销合同",
    "framework_contract": "框架合同",
    "service_contract": "服务合同",
    "labor_contract": "劳务合同",
    "lease_contract": "租赁合同",
    "nda_agreement": "保密协议",
    "contract_generic": "普通合同",
    "vat_special_invoice": "增值税专用发票",
    "vat_general_invoice": "增值税普通发票",
    "proforma_invoice": "形式发票",
    "sales_invoice": "销项发票",
    "purchase_invoice": "进项发票",
    "invoice_generic": "普通发票",
    "import_customs_declaration": "进口报关单",
    "export_customs_declaration": "出口报关单",
    "import_packing_list": "进口装箱单",
    "export_packing_list": "出口装箱单",
    "packing_list_generic": "装箱单",
    "master_bill_of_lading": "主提单",
    "house_bill_of_lading": "分提单",
    "ocean_bill_of_lading": "海运提单",
    "bill_of_lading_generic": "提单",
    "master_air_waybill": "主空运单",
    "house_air_waybill": "分空运单",
    "air_waybill_generic": "空运运单",
    "coo_form_e": "原产地证（Form E）",
    "coo_form_a": "原产地证（Form A）",
    "certificate_of_origin_generic": "原产地证",
    "advance_payment": "预付款",
    "final_payment": "尾款",
    "payment_generic": "付款单",
    "travel_expense": "差旅报销",
    "marketing_expense": "营销报销",
    "expense_generic": "报销单",
}

STAGE_PROGRESS = {
    "pending": 0,
    "pending_docs": 8,
    "ocr": 30,
    "extract": 55,
    "rules": 70,
    "ai": 85,
    "review": 92,
    "erp_pending_sync": 97,
    "report": 95,
    "done": 100,
    "failed": 100,
}
AUDIT_JOB_DB_UPDATE_FIELDS = {
    "doc_type",
    "model_type",
    "status",
    "progress",
    "stage",
    "error_message",
    "file_url",
    "file_name",
}

AUDIT_MODEL_ALIASES = {
    "local": "local",
    "cloud": "cloud",
    "deepseek": "cloud",
    "auto": "local",
}

OCR_REQUIRED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
DIRECT_PARSE_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
AUDIT_PDF_FAST_PARSE_ENABLED = os.getenv("AUDIT_PDF_FAST_PARSE_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
AUDIT_PDF_FAST_PARSE_MIN_CHARS = int(os.getenv("AUDIT_PDF_FAST_PARSE_MIN_CHARS", "180"))

DATE_COMPACT_PATTERN = r"\b(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\b"
AMOUNT_CAPTURE_PATTERN = r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?"
AMOUNT_TOKEN_PATTERN = rf"(?<![\dA-Za-z])({AMOUNT_CAPTURE_PATTERN})(?![\dA-Za-z])"

AUDIT_JOBS: Dict[str, Dict[str, Any]] = {}
AUDIT_LOCK = threading.Lock()
AUDIT_CASES: Dict[str, Dict[str, Any]] = {}
AUDIT_CASE_LOCK = threading.Lock()
ERP_SYNC_QUEUE: Dict[str, Dict[str, Any]] = {}
ERP_SYNC_LOCK = threading.Lock()
_OCR_ENGINE: Optional[OCRManager] = None
_OCR_ENGINE_LOCK = threading.Lock()
_AUDIT_DB_SCHEMA_LOCK = threading.Lock()
_AUDIT_DB_UNSUPPORTED_COLUMNS: Dict[str, set[str]] = {}


class AuditFields(BaseModel):
    doc_type: Optional[str] = None
    doc_subtype: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    invoice_no: Optional[str] = None
    tax_no: Optional[str] = None
    vendor: Optional[str] = None
    contract_no: Optional[str] = None
    po_no: Optional[str] = None
    declaration_no: Optional[str] = None
    packing_list_no: Optional[str] = None
    bl_awb_no: Optional[str] = None
    hs_code: Optional[str] = None
    incoterm: Optional[str] = None
    origin_country: Optional[str] = None
    destination_country: Optional[str] = None
    port_loading: Optional[str] = None
    port_discharge: Optional[str] = None
    customs_duty_amount: Optional[float] = None
    vat_amount: Optional[float] = None
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


def _doc_type_display_name(doc_type: Optional[str]) -> str:
    normalized = normalize_doc_type(doc_type)
    return DOC_TYPE_DISPLAY_NAMES.get(normalized, normalized or "未知类型")


def _doc_subtype_display_name(doc_subtype: Optional[str]) -> str:
    code = _safe_text(doc_subtype)
    if not code:
        return ""
    return DOC_SUBTYPE_DISPLAY_NAMES.get(code, code)


def _append_doc_type_to_summary(summary: Optional[str], doc_type: Optional[str], doc_subtype: Optional[str] = None) -> str:
    normalized = normalize_doc_type(doc_type)
    label = _doc_type_display_name(normalized)
    head = f"识别单据类型：{label}（{normalized}）" if normalized and normalized != "auto" else f"识别单据类型：{label}"
    subtype_code = _safe_text(doc_subtype)
    subtype_label = _doc_subtype_display_name(subtype_code)
    if subtype_code:
        head = f"{head}；细分类：{subtype_label}（{subtype_code}）" if subtype_label != subtype_code else f"{head}；细分类：{subtype_code}"
    text = _safe_text(summary)
    if not text:
        return head
    if "识别单据类型" in text:
        if subtype_code and "细分类" not in text:
            subtype_line = f"细分类：{subtype_label}（{subtype_code}）" if subtype_label != subtype_code else f"细分类：{subtype_code}"
            return f"{text}\n{subtype_line}"
        return text
    if normalized and normalized != "auto" and normalized in text[:160]:
        return text
    if label and label in text[:160]:
        return text
    return f"{head}。\n{text}"


def normalize_model_type(model_type: Optional[str]) -> str:
    key = (model_type or "").strip().lower()
    if not key:
        return AUDIT_AI_BACKEND
    return AUDIT_MODEL_ALIASES.get(key, AUDIT_AI_BACKEND)


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


def _normalize_text(value: Any) -> str:
    text = _safe_text(value).lower()
    if not text:
        return ""
    text = re.sub(r"[\s\u3000]+", "", text)
    # 仅保留字母/数字/中文；去除标点符号以实现稳定的 ID/供应商匹配。
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text


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
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
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
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    if not OCRManager:
        return None
    with _OCR_ENGINE_LOCK:
        if _OCR_ENGINE is None:
            if get_shared_ocr_manager:
                _OCR_ENGINE = get_shared_ocr_manager()
            else:
                _OCR_ENGINE = OCRManager()
    return _OCR_ENGINE


def _ensure_storage_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _sanitize_db_payload(table: str, payload: Any) -> Any:
    with _AUDIT_DB_SCHEMA_LOCK:
        unsupported = set(_AUDIT_DB_UNSUPPORTED_COLUMNS.get(table) or set())
    if not unsupported:
        return payload
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k not in unsupported}
    if isinstance(payload, list):
        sanitized_items = []
        for item in payload:
            if isinstance(item, dict):
                sanitized_items.append({k: v for k, v in item.items() if k not in unsupported})
            else:
                sanitized_items.append(item)
        return sanitized_items
    return payload


def _record_missing_db_column(table: str, error: Exception) -> Optional[str]:
    message = str(error or "")
    match = re.search(
        rf"Could not find the '([^']+)' column of '{re.escape(table)}' in the schema cache",
        message,
    )
    if not match:
        return None
    column = _safe_text(match.group(1))
    if not column:
        return None
    with _AUDIT_DB_SCHEMA_LOCK:
        _AUDIT_DB_UNSUPPORTED_COLUMNS.setdefault(table, set()).add(column)
    print(f"[Audit DB] Skip unsupported column '{column}' for table '{table}'")
    return column


def _audit_state_file_path(root: str, item_id: str) -> str:
    safe_item_id = re.sub(r"[^A-Za-z0-9_\-]", "_", str(item_id or "").strip())
    if not safe_item_id:
        raise ValueError("State item id is required")
    _ensure_storage_dir(root)
    return os.path.join(root, f"{safe_item_id}.json")


def _read_json_file(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json_file(path: str, payload: Dict[str, Any]) -> None:
    target_dir = os.path.dirname(path)
    if target_dir:
        _ensure_storage_dir(target_dir)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _persist_job_state(job_payload: Dict[str, Any]) -> None:
    if not isinstance(job_payload, dict):
        return
    job_id = _safe_text(job_payload.get("job_id"))
    if not job_id:
        return
    try:
        _write_json_file(_audit_state_file_path(AUDIT_JOB_STATE_DIR, job_id), job_payload)
    except Exception as e:
        print(f"[Audit State] Persist job failed ({job_id}): {e}")


def _load_job_state(job_id: str) -> Optional[Dict[str, Any]]:
    job_key = _safe_text(job_id)
    if not job_key:
        return None
    return _read_json_file(_audit_state_file_path(AUDIT_JOB_STATE_DIR, job_key))


def _persist_case_state(case_payload: Dict[str, Any]) -> None:
    if not isinstance(case_payload, dict):
        return
    case_id = _safe_text(case_payload.get("case_id"))
    if not case_id:
        return
    try:
        _write_json_file(_audit_state_file_path(AUDIT_CASE_STATE_DIR, case_id), case_payload)
    except Exception as e:
        print(f"[Audit State] Persist case failed ({case_id}): {e}")


def _load_case_state(case_id: str) -> Optional[Dict[str, Any]]:
    case_key = _normalize_case_id(case_id)
    if not case_key:
        return None
    return _read_json_file(_audit_state_file_path(AUDIT_CASE_STATE_DIR, case_key))


def _persist_erp_queue_state(task_payload: Dict[str, Any]) -> None:
    if not isinstance(task_payload, dict):
        return
    queue_id = _safe_text(task_payload.get("queue_id"))
    if not queue_id:
        return
    try:
        _write_json_file(_audit_state_file_path(AUDIT_ERP_QUEUE_STATE_DIR, queue_id), task_payload)
    except Exception as e:
        print(f"[Audit State] Persist ERP queue failed ({queue_id}): {e}")


def _hydrate_case_from_storage(case_id: Optional[str]) -> Optional[Dict[str, Any]]:
    normalized_case_id = _normalize_case_id(case_id)
    if not normalized_case_id:
        return None
    with AUDIT_CASE_LOCK:
        existing = AUDIT_CASES.get(normalized_case_id)
        if existing:
            return existing
    persisted = _load_case_state(normalized_case_id)
    if not persisted:
        return None
    with AUDIT_CASE_LOCK:
        current = AUDIT_CASES.get(normalized_case_id)
        if current:
            return current
        AUDIT_CASES[normalized_case_id] = persisted
        return AUDIT_CASES[normalized_case_id]


def _hydrate_job_from_storage(job_id: str) -> Optional[Dict[str, Any]]:
    job_key = _safe_text(job_id)
    if not job_key:
        return None
    with AUDIT_LOCK:
        existing = AUDIT_JOBS.get(job_key)
        if existing:
            return existing
    persisted = _load_job_state(job_key) or _load_job_from_db(job_key)
    if not persisted:
        return None
    case_id = _normalize_case_id(persisted.get("case_id"))
    if case_id:
        _hydrate_case_from_storage(case_id)
    with AUDIT_LOCK:
        current = AUDIT_JOBS.get(job_key)
        if current:
            return current
        AUDIT_JOBS[job_key] = persisted
        return AUDIT_JOBS[job_key]


def _normalize_case_id(case_id: Optional[str]) -> Optional[str]:
    text = _safe_text(case_id)
    if not text:
        return None
    # Keep case id URL-safe and deterministic for storage/indexing.
    if re.fullmatch(r"[A-Za-z0-9_\-]{8,80}", text):
        return text
    return None


def _ensure_case(case_id: str, user_id: str, doc_type: str = "auto") -> Dict[str, Any]:
    now = _now_iso()
    _hydrate_case_from_storage(case_id)
    case_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_CASE_LOCK:
        case = AUDIT_CASES.get(case_id)
        if case is None:
            case = {
                "case_id": case_id,
                "user_id": user_id or "anonymous",
                "doc_type_hint": normalize_doc_type(doc_type),
                "created_at": now,
                "updated_at": now,
                "documents": [],
                "latest_job_id": None,
            }
            AUDIT_CASES[case_id] = case
        else:
            case["updated_at"] = now
            if user_id:
                case["user_id"] = user_id
            if doc_type:
                case["doc_type_hint"] = normalize_doc_type(doc_type)
        case_snapshot = dict(case)
    if case_snapshot:
        _persist_case_state(case_snapshot)
    return case_snapshot or {}


def _case_public_documents(case_id: Optional[str]) -> List[Dict[str, Any]]:
    if not case_id:
        return []
    _hydrate_case_from_storage(case_id)
    with AUDIT_CASE_LOCK:
        case = AUDIT_CASES.get(case_id) or {}
        documents = case.get("documents") or []
        output: List[Dict[str, Any]] = []
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            output.append(
                {
                    "job_id": doc.get("job_id"),
                    "doc_id": doc.get("doc_id"),
                    "file_name": doc.get("file_name"),
                    "file_url": doc.get("file_url"),
                    "doc_type": doc.get("doc_type"),
                    "tag": doc.get("tag"),
                    "extract_mode": doc.get("extract_mode"),
                    "ocr_confidence": doc.get("ocr_confidence"),
                    "status": doc.get("status"),
                    "updated_at": doc.get("updated_at"),
                }
            )
        return output


def _detect_case_doc_tag(file_name: str, doc_type: str) -> str:
    normalized_type = normalize_doc_type(doc_type)
    direct_map = {
        "contract": "contract",
        "invoice": "invoice",
        "payment": "payment",
        "expense": "expense",
        "packing_list": "packing_list",
        "bill_of_lading": "bill_of_lading",
        "air_waybill": "air_waybill",
        "certificate_of_origin": "certificate_of_origin",
        "import_declaration": "customs_declaration",
        "export_declaration": "customs_declaration",
    }
    if normalized_type in direct_map:
        return direct_map[normalized_type]

    name = _safe_text(file_name).lower()
    patterns = [
        (("contract", "合同"), "contract"),
        (("invoice", "发票"), "invoice"),
        (("packing", "装箱"), "packing_list"),
        (("bill of lading", "提单", "b/l"), "bill_of_lading"),
        (("air waybill", "airwaybill", "awb", "运单"), "air_waybill"),
        (("origin", "原产地"), "certificate_of_origin"),
        (("declaration", "报关"), "customs_declaration"),
        (("po", "purchase order", "采购单"), "purchase_order"),
    ]
    for keys, tag in patterns:
        if any(k in name for k in keys):
            return tag
    return "other"


def _is_contract_like_upload(doc_type: str, file_name: str) -> bool:
    normalized = normalize_doc_type(doc_type)
    if normalized == "contract":
        return True
    if normalized != "auto":
        return False
    name = _safe_text(file_name).lower()
    return any(token in name for token in ("合同", "contract", "agreement", "协议"))


def _case_has_contract_document(case_id: Optional[str]) -> bool:
    if not case_id:
        return False
    docs = _case_public_documents(case_id)
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        status = _safe_text(doc.get("status")).lower()
        if status in {"failed", "cancelled"}:
            continue
        tag = _safe_text(doc.get("tag")).lower()
        dtype = normalize_doc_type(doc.get("doc_type"))
        if tag == "contract" or dtype == "contract":
            return True
    return False


def _resolve_upload_sequence_step(doc_type: str, file_name: str) -> int:
    normalized = normalize_doc_type(doc_type)
    if normalized == "contract":
        return 1
    if normalized in {
        "invoice",
        "packing_list",
        "bill_of_lading",
        "air_waybill",
        "import_declaration",
        "export_declaration",
        "certificate_of_origin",
        "trade_case",
    }:
        return 2
    if normalized in {"payment", "expense"}:
        return 3
    if normalized == "auto":
        inferred_tag = _detect_case_doc_tag(file_name, normalized)
        if inferred_tag == "contract":
            return 1
        if inferred_tag in {"invoice", "packing_list", "bill_of_lading", "air_waybill", "customs_declaration", "certificate_of_origin", "purchase_order"}:
            return 2
        if inferred_tag in {"payment", "expense"}:
            return 3
    return 2


def _case_has_trade_document(case_id: Optional[str]) -> bool:
    if not case_id:
        return False
    docs = _case_public_documents(case_id)
    trade_tags = {"invoice", "packing_list", "bill_of_lading", "air_waybill", "customs_declaration", "certificate_of_origin", "purchase_order"}
    trade_doc_types = {
        "invoice",
        "packing_list",
        "bill_of_lading",
        "air_waybill",
        "import_declaration",
        "export_declaration",
        "certificate_of_origin",
        "trade_case",
    }
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        status = _safe_text(doc.get("status")).lower()
        if status in {"failed", "cancelled"}:
            continue
        tag = _safe_text(doc.get("tag")).lower()
        dtype = normalize_doc_type(doc.get("doc_type"))
        if tag in trade_tags or dtype in trade_doc_types:
            return True
    return False


def _add_case_document_entry(
    *,
    case_id: Optional[str],
    job_id: str,
    doc_id: str,
    file_name: str,
    file_url: str,
    doc_type: str,
) -> None:
    if not case_id:
        return
    now = _now_iso()
    case_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_CASE_LOCK:
        case = AUDIT_CASES.get(case_id)
        if not case:
            return
        docs = case.setdefault("documents", [])
        docs.append(
            {
                "job_id": job_id,
                "doc_id": doc_id,
                "file_name": file_name,
                "file_url": file_url,
                "doc_type": normalize_doc_type(doc_type),
                "tag": _detect_case_doc_tag(file_name, doc_type),
                "status": "uploaded",
                "extract_mode": None,
                "ocr_confidence": None,
                "raw_text": "",
                "updated_at": now,
            }
        )
        case["updated_at"] = now
        case["latest_job_id"] = job_id
        case_snapshot = dict(case)
    if case_snapshot:
        _persist_case_state(case_snapshot)


def _update_case_document_entry(
    *,
    case_id: Optional[str],
    job_id: str,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    extract_mode: Optional[str] = None,
    ocr_confidence: Optional[float] = None,
    raw_text: Optional[str] = None,
) -> None:
    if not case_id:
        return
    now = _now_iso()
    case_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_CASE_LOCK:
        case = AUDIT_CASES.get(case_id)
        if not case:
            return
        docs = case.get("documents") or []
        for doc in docs:
            if not isinstance(doc, dict) or _safe_text(doc.get("job_id")) != _safe_text(job_id):
                continue
            if doc_type:
                normalized_doc_type = normalize_doc_type(doc_type)
                doc["doc_type"] = normalized_doc_type
                doc["tag"] = _detect_case_doc_tag(doc.get("file_name") or "", normalized_doc_type)
            if status:
                doc["status"] = status
            if extract_mode:
                doc["extract_mode"] = extract_mode
            if ocr_confidence is not None:
                doc["ocr_confidence"] = ocr_confidence
            if raw_text is not None:
                doc["raw_text"] = raw_text
            doc["updated_at"] = now
            break
        case["updated_at"] = now
        case["latest_job_id"] = job_id
        case_snapshot = dict(case)
    if case_snapshot:
        _persist_case_state(case_snapshot)


def _build_case_combined_text(case_id: Optional[str], current_job_id: str, current_text: str) -> str:
    if not case_id:
        return current_text
    segments: List[str] = []
    current_included = False
    with AUDIT_CASE_LOCK:
        case = AUDIT_CASES.get(case_id) or {}
        docs = case.get("documents") or []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            text = _safe_text(doc.get("raw_text"))
            if not text:
                continue
            title = _safe_text(doc.get("file_name")) or _safe_text(doc.get("doc_type")) or "document"
            if _safe_text(doc.get("job_id")) == _safe_text(current_job_id):
                current_included = True
            segments.append(f"[文档]{title}\n{text}")
    if current_text and _safe_text(current_text) and not current_included:
        current_title = f"[当前上传] job={current_job_id}"
        segments.append(f"{current_title}\n{current_text}")
    if not segments:
        return current_text
    merged = "\n\n".join(segments)
    # Keep extraction context bounded for latency and token budget.
    return merged[-18000:]


def _evaluate_case_completeness(case_documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    tags = {str(doc.get("tag") or "") for doc in (case_documents or [])}
    required = ["contract", "invoice", "packing_list", "bill_of_lading"]
    present = [tag for tag in required if tag in tags]
    missing = [tag for tag in required if tag not in tags]
    return {
        "required": required,
        "present": present,
        "missing": missing,
        "complete": len(missing) == 0,
        "total_documents": len(case_documents or []),
    }


def _save_local_file(file_bytes: bytes, user_id: str, job_id: str, filename: str) -> Tuple[str, str]:
    safe_name = filename.replace("\\", "_").replace("/", "_")
    target_dir = os.path.join(LOCAL_STORAGE_ROOT, user_id, job_id)
    _ensure_storage_dir(target_dir)
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    relative_path = f"audit/{user_id}/{job_id}/{safe_name}"
    return target_path, relative_path


def _normalize_audit_relative_path(file_url: Optional[str]) -> str:
    normalized = _safe_text(file_url).replace("\\", "/").strip()
    if not normalized:
        return ""
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    for prefix in ("api/static/", "static/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized.strip("/")


def _resolve_audit_local_path(
    file_url: Optional[str],
    *,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    file_name: Optional[str] = None,
    local_path_hint: Optional[str] = None,
) -> Optional[str]:
    candidates: List[str] = []
    hint = _safe_text(local_path_hint)
    if hint:
        candidates.append(hint)

    normalized_file_url = _normalize_audit_relative_path(file_url)
    if normalized_file_url:
        if os.path.isabs(normalized_file_url):
            candidates.append(normalized_file_url)
        if normalized_file_url.startswith("audit/"):
            relative_tail = normalized_file_url.split("/", 1)[1] if "/" in normalized_file_url else ""
            if relative_tail:
                candidates.append(os.path.join(LOCAL_STORAGE_ROOT, relative_tail.replace("/", os.sep)))
            candidates.append(os.path.join(os.path.dirname(LOCAL_STORAGE_ROOT), normalized_file_url.replace("/", os.sep)))
            candidates.append(os.path.join(BASE_DIR, "storage", normalized_file_url.replace("/", os.sep)))
        else:
            candidates.append(os.path.join(LOCAL_STORAGE_ROOT, normalized_file_url.replace("/", os.sep)))
            candidates.append(os.path.join(BASE_DIR, "storage", normalized_file_url.replace("/", os.sep)))

    safe_user_id = _safe_text(user_id) or "anonymous"
    safe_job_id = _safe_text(job_id)
    safe_file_name = _safe_text(file_name).replace("\\", "_").replace("/", "_")
    if safe_job_id and safe_file_name:
        candidates.append(os.path.join(LOCAL_STORAGE_ROOT, safe_user_id, safe_job_id, safe_file_name))

    deduped_candidates: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = os.path.normpath(str(candidate or "").strip())
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        deduped_candidates.append(normalized_candidate)

    for candidate in deduped_candidates:
        if os.path.exists(candidate):
            return candidate
    return deduped_candidates[0] if deduped_candidates else None


def _insert_db(table: str, payload: Any) -> None:
    if not require_supabase:
        return
    sanitized_payload = _sanitize_db_payload(table, payload)
    try:
        sb = require_supabase()
        sb.table(table).insert(sanitized_payload).execute()
    except Exception as e:
        missing_column = _record_missing_db_column(table, e)
        if missing_column:
            retry_payload = _sanitize_db_payload(table, sanitized_payload)
            if retry_payload != sanitized_payload:
                try:
                    sb = require_supabase()
                    sb.table(table).insert(retry_payload).execute()
                    return
                except Exception as retry_error:
                    print(f"[Audit DB] Insert retry failed ({table}): {retry_error}")
        print(f"[Audit DB] Insert failed ({table}): {e}")


def _update_db(table: str, payload: Dict[str, Any], job_id: str, key: str = "job_id") -> None:
    if not require_supabase:
        return
    sanitized_payload = _sanitize_db_payload(table, payload)
    if not sanitized_payload:
        return
    try:
        sb = require_supabase()
        sb.table(table).update(sanitized_payload).eq(key, job_id).execute()
    except Exception as e:
        missing_column = _record_missing_db_column(table, e)
        if missing_column:
            retry_payload = _sanitize_db_payload(table, sanitized_payload)
            if retry_payload != sanitized_payload:
                try:
                    sb = require_supabase()
                    sb.table(table).update(retry_payload).eq(key, job_id).execute()
                    return
                except Exception as retry_error:
                    print(f"[Audit DB] Update retry failed ({table}): {retry_error}")
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
        result_case_summary = result.get("case_summary") if isinstance(result, dict) else {}
        case_id = _safe_text(result_case_summary.get("case_id")) if isinstance(result_case_summary, dict) else ""
        case_documents = result_case_summary.get("documents") if isinstance(result_case_summary, dict) else []
        if not isinstance(case_documents, list):
            case_documents = []
        return {
            "job_id": job.get("job_id"),
            "user_id": job.get("user_id"),
            "doc_type": job.get("doc_type"),
            "model_type": normalize_model_type(job.get("model_type")),
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "stage": job.get("stage"),
            "workflow_state": job.get("workflow_state"),
            "error_message": job.get("error_message"),
            "file_url": file_url,
            "file_name": file_name,
            "case_id": case_id or None,
            "case_documents": case_documents,
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
    case_id: Optional[str] = None,
    model_type: Optional[str] = None,
) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    normalized_doc_type = normalize_doc_type(doc_type)
    normalized_model_type = normalize_model_type(model_type)
    safe_user_id = user_id or "anonymous"
    normalized_case_id = _normalize_case_id(case_id) or str(uuid.uuid4())
    _ensure_case(normalized_case_id, safe_user_id, normalized_doc_type)

    existing_case_docs = _case_public_documents(normalized_case_id)
    upload_step = _resolve_upload_sequence_step(normalized_doc_type, filename)
    if existing_case_docs:
        has_contract_doc = _case_has_contract_document(normalized_case_id)
        has_trade_doc = _case_has_trade_document(normalized_case_id)
        if not has_contract_doc and upload_step != 1:
            raise ValueError("当前审单包尚未上传合同主文档，请先上传合同后再上传其他单据。")
        if upload_step == 3 and not has_trade_doc:
            raise ValueError("请先上传至少一份履约/贸易单据（如发票、提单、装箱单）后，再上传付款或报销单据。")
    else:
        if upload_step != 1:
            raise ValueError("新审单包请先上传合同主文档（建议将单据类型切换为“合同”）。")

    local_path, file_url = _save_local_file(file_bytes, safe_user_id, job_id, filename)
    file_url = file_url.replace("\\", "/")

    job = {
        "job_id": job_id,
        "doc_id": doc_id,
        "user_id": safe_user_id,
        "doc_type": normalized_doc_type,
        "case_id": normalized_case_id,
        "model_type": normalized_model_type,
        "status": "pending",
        "progress": 0,
        "stage": "pending_docs",
        "workflow_state": "pending_docs",
        "error_message": None,
        "file_url": file_url,
        "local_path": local_path,
        "file_name": filename,
        "result": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    with AUDIT_LOCK:
        AUDIT_JOBS[job_id] = job
    _persist_job_state(job)

    _insert_db("audit_jobs", {
        "job_id": job_id,
        "user_id": safe_user_id,
        "doc_type": normalized_doc_type,
        "model_type": normalized_model_type,
        "status": "pending",
        "progress": 0,
        "stage": "pending_docs",
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
    _add_case_document_entry(
        case_id=normalized_case_id,
        job_id=job_id,
        doc_id=doc_id,
        file_name=filename,
        file_url=file_url,
        doc_type=normalized_doc_type,
    )

    return job


def update_job(job_id: str, **updates: Any) -> None:
    now_iso = _now_iso()
    job_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            job = _load_job_state(job_id) or _load_job_from_db(job_id)
            if job:
                AUDIT_JOBS[job_id] = job
        if job:
            job.update(updates)
            job["updated_at"] = now_iso
            job_snapshot = dict(job)
    if job_snapshot:
        _persist_job_state(job_snapshot)

    payload = {k: v for k, v in updates.items() if k in AUDIT_JOB_DB_UPDATE_FIELDS}
    if payload:
        payload["updated_at"] = now_iso
        _update_db("audit_jobs", payload, job_id)


def _is_cancelled(job_id: str) -> bool:
    job = _hydrate_job_from_storage(job_id)
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
    job_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            job = _load_job_state(job_id) or _load_job_from_db(job_id)
            if job:
                AUDIT_JOBS[job_id] = job
        if job:
            found = True
            job["cancelled"] = True
            job["status"] = "cancelled"
            job["stage"] = "cancelled"
            job["progress"] = 100
            job["updated_at"] = _now_iso()
            job_snapshot = dict(job)
    if job_snapshot:
        _persist_job_state(job_snapshot)

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
    job = _hydrate_job_from_storage(job_id)
    if not job:
        job = _load_job_from_db(job_id)
    if not job:
        return False, "Job not found"
    user_id = job.get("user_id") or "anonymous"
    file_url = job.get("file_url")
    file_name = job.get("file_name") or os.path.basename(str(file_url or "")) or "document"
    if not file_url:
        return False, "Missing file path"
    local_path = _resolve_audit_local_path(
        file_url,
        user_id=user_id,
        job_id=job_id,
        file_name=file_name,
        local_path_hint=job.get("local_path"),
    )
    if not local_path or not os.path.exists(local_path):
        return False, f"File not found: {local_path}"
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        enqueue_audit_job(
            file_bytes,
            file_name,
            user_id,
            job.get("doc_type", "auto"),
            case_id=job.get("case_id"),
            model_type=job.get("model_type"),
        )
        return True, None
    except Exception as e:
        return False, str(e)


def get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    snapshot = _load_job_from_db(job_id)
    local_job = _hydrate_job_from_storage(job_id)
    if snapshot:
        if local_job:
            if not snapshot.get("case_id"):
                snapshot["case_id"] = local_job.get("case_id")
            snapshot["workflow_state"] = local_job.get("workflow_state") or snapshot.get("workflow_state")
            if not snapshot.get("case_documents"):
                snapshot["case_documents"] = _case_public_documents(local_job.get("case_id"))
            if not snapshot.get("result") and local_job.get("result"):
                snapshot["result"] = local_job.get("result")
        return snapshot
    job = local_job
    if job:
        return {
            "job_id": job["job_id"],
            "user_id": job.get("user_id"),
            "status": job["status"],
            "progress": job.get("progress", 0),
            "stage": job.get("stage"),
            "workflow_state": job.get("workflow_state"),
            "error_message": job.get("error_message"),
            "result": job.get("result"),
            "doc_type": job.get("doc_type"),
            "model_type": job.get("model_type"),
            "file_url": job.get("file_url"),
            "file_name": job.get("file_name"),
            "case_id": job.get("case_id"),
            "case_documents": _case_public_documents(job.get("case_id")),
        }
    return None


def list_local_audit_jobs(limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    ensure_runtime_layout()
    if limit <= 0:
        return []
    try:
        job_files = [
            os.path.join(AUDIT_JOB_STATE_DIR, item)
            for item in os.listdir(AUDIT_JOB_STATE_DIR)
            if str(item).endswith(".json")
        ]
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[Audit State] List jobs failed: {e}")
        return []

    rows: List[Dict[str, Any]] = []
    for path in job_files:
        try:
            payload = _read_json_file(path)
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            continue
        rows.append(payload)

    rows.sort(
        key=lambda item: (
            _safe_text(item.get("created_at") or item.get("updated_at")),
            _safe_text(item.get("job_id")),
        ),
        reverse=True,
    )
    if offset:
        rows = rows[offset:]
    return rows[:limit]


DATE_PATTERN = r"(?:19|20)\d{2}\s*(?:[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}|\u5e74\s*\d{1,2}\s*\u6708\s*\d{1,2}\s*\u65e5?)"


def _is_compact_date_digits(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    if not re.fullmatch(r"(?:19|20)\d{6}", digits):
        return False
    year = int(digits[:4])
    month = int(digits[4:6])
    day = int(digits[6:8])
    if month < 1 or month > 12:
        return False
    if day < 1 or day > 31:
        return False
    return 1900 <= year <= 2099


def _normalize_date_token(value: Any) -> Optional[str]:
    text = _safe_text(value)
    if not text:
        return None
    m = re.search(r"((?:19|20)\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"((?:19|20)\d{2})\s*\u5e74\s*(\d{1,2})\s*\u6708\s*(\d{1,2})\s*\u65e5?", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if _is_compact_date_digits(text):
        digits = re.sub(r"\D", "", text)
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _looks_like_date_token(value: Any) -> bool:
    return _normalize_date_token(value) is not None


def _extract_dates(text: str) -> List[str]:
    dates: List[str] = []
    for m in re.findall(DATE_PATTERN, text or ""):
        normalized = _normalize_date_token(m)
        if normalized:
            dates.append(normalized)
    return dates


def _find_date_by_keywords(text: str, keywords: List[str]) -> Optional[str]:
    if not text:
        return None
    for kw in keywords:
        pattern = rf"{kw}\s*[:\uFF1A]?\s*({DATE_PATTERN})"
        m = re.search(pattern, text)
        if m:
            normalized = _normalize_date_token(m.group(1))
            if normalized:
                return normalized
    return None


def _normalize_amount_value(value: Any) -> Optional[float]:
    text = _safe_text(value)
    if not text or _looks_like_date_token(text):
        return None

    alpha_tokens = re.findall(r"[A-Za-z]+", text)
    if alpha_tokens:
        allowed_currency_tokens = {"rmb", "cny", "usd", "eur", "hkd", "jpy"}
        if any(token.lower() not in allowed_currency_tokens for token in alpha_tokens):
            return None

    cleaned = text.replace(",", "").strip()
    cleaned = re.sub(r"^[^0-9+\-]+", "", cleaned)
    cleaned = re.sub(r"[^0-9.]+$", "", cleaned)
    if not cleaned or cleaned in {"+", "-"}:
        return None
    if cleaned.count(".") > 1:
        return None

    val = _safe_float(cleaned)
    if val is None:
        return None
    abs_val = abs(val)
    if abs_val > 1e9:
        return None

    digit_count = len(re.sub(r"\D", "", cleaned))
    if "." not in cleaned and digit_count >= 10:
        return None
    if "." not in cleaned and 1900 <= abs_val <= 2100 and digit_count <= 4:
        return None
    return round(val, 2)


def _is_amount_date_context(text: str, start: int, end: int, raw: str) -> bool:
    window = text[max(0, start - 18): min(len(text), end + 18)]
    if re.search(r"(?:19|20)\d{2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}", window):
        return True
    if re.search(r"(?:19|20)\d{2}\s*\u5e74\s*\d{1,2}\s*\u6708\s*\d{1,2}\s*\u65e5?", window):
        return True
    return _is_compact_date_digits(raw)


def _is_identifier_context(text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 10): min(len(text), end + 10)].lower()
    return bool(
        re.search(
            r"(?:"
            r"\u8d26\u53f7|\u8d26\u6237|\u5f00\u6237|\u7a0e\u53f7|\u7f16\u53f7|\u5355\u53f7|"
            r"\u53d1\u7968\u53f7|\u5408\u540c\u53f7|account|invoice|contract|tax|serial|no\."
            r")",
            context,
        )
    )


def _amount_signal_score(text: str, start: int, end: int, raw: str, amount: float) -> int:
    score = 0
    context = text[max(0, start - 16): min(len(text), end + 16)]
    if re.search(r"(?:\u00a5|\uffe5|\$|USD|CNY|RMB)", context, flags=re.IGNORECASE):
        score += 2
    if re.search(r"(?:\u91d1\u989d|\u5408\u8ba1|\u603b\u8ba1|\u4ef7\u7a0e|\u5e94\u4ed8|\u4ed8\u6b3e|\u62a5\u9500)", context):
        score += 2
    if "." in raw or "," in raw:
        score += 1
    if abs(amount) >= 1000:
        score += 1
    return score


def _extract_amount_candidates(text: str) -> List[Tuple[float, int, int]]:
    candidates: List[Tuple[float, int, int]] = []
    for match in re.finditer(AMOUNT_TOKEN_PATTERN, text or ""):
        raw = match.group(1)
        start, end = match.span(1)
        amount = _normalize_amount_value(raw)
        if amount is None:
            continue
        if _is_amount_date_context(text or "", start, end, raw):
            continue
        if _is_identifier_context(text or "", start, end):
            continue
        score = _amount_signal_score(text or "", start, end, raw, amount)
        candidates.append((amount, score, start))
    return candidates


def _extract_amounts(text: str) -> List[float]:
    return [item[0] for item in _extract_amount_candidates(text)]


def _find_amount_by_keywords(text: str, keywords: List[str]) -> Optional[float]:
    candidates: List[Tuple[float, int, int]] = []
    source = text or ""
    for kw in keywords:
        kw_escaped = re.escape(str(kw))
        pattern = rf"{kw_escaped}\s*[:\uFF1A]?\s*(?:\u4eba\u6c11\u5e01|RMB|CNY|USD|\$|\u00a5|\uffe5)?\s*({AMOUNT_CAPTURE_PATTERN})"
        for match in re.finditer(pattern, source, flags=re.IGNORECASE):
            raw = match.group(1)
            start, end = match.span(1)
            amount = _normalize_amount_value(raw)
            if amount is None:
                continue
            if _is_amount_date_context(source, start, end, raw):
                continue
            score = _amount_signal_score(source, start, end, raw, amount) + 3
            candidates.append((amount, score, start))

    if not candidates:
        for line in source.splitlines():
            if not line.strip():
                continue
            if any(kw in line for kw in keywords):
                line_candidates = _extract_amount_candidates(line)
                if line_candidates:
                    line_candidates.sort(key=lambda item: (item[1], item[0], -item[2]), reverse=True)
                    return line_candidates[0][0]
        return None

    candidates.sort(key=lambda item: (item[1], item[0], -item[2]), reverse=True)
    return candidates[0][0]


AUDIT_DOC_TYPES = [
    "invoice",
    "contract",
    "payment",
    "expense",
    "trade_case",
    "import_declaration",
    "export_declaration",
    "packing_list",
    "bill_of_lading",
    "air_waybill",
    "certificate_of_origin",
]
AUDIT_FIELD_KEYS = [
    "doc_subtype",
    "total_amount",
    "currency",
    "exchange_rate",
    "invoice_no",
    "tax_no",
    "vendor",
    "contract_no",
    "po_no",
    "declaration_no",
    "packing_list_no",
    "bl_awb_no",
    "hs_code",
    "incoterm",
    "origin_country",
    "destination_country",
    "port_loading",
    "port_discharge",
    "customs_duty_amount",
    "vat_amount",
    "contract_date",
    "invoice_date",
    "payment_date",
    "payee",
    "bank_account",
    "reimburser",
]
AUDIT_AMOUNT_KEYWORDS = [
    "\u4ef7\u7a0e\u5408\u8ba1",
    "\u5408\u8ba1",
    "\u603b\u8ba1",
    "\u91d1\u989d",
    "\u5e94\u4ed8",
    "\u4ed8\u6b3e\u91d1\u989d",
    "\u62a5\u9500\u91d1\u989d",
]


def _has_amount_keyword(text: str) -> bool:
    source = text or ""
    if not source:
        return False
    extra_keywords = [
        "\u5408\u540c\u91d1\u989d",
        "\u542b\u7a0e\u91d1\u989d",
        "\u672a\u7a0e\u91d1\u989d",
        "\u603b\u989d",
        "\u603b\u4ef7",
        "\u5b9e\u4ed8",
        "\u91d1\u989d\uff08\u5927\u5199\uff09",
        "\u91d1\u989d(\u5927\u5199)",
    ]
    for kw in [*AUDIT_AMOUNT_KEYWORDS, *extra_keywords]:
        if kw and kw in source:
            return True
    return False


def _is_identifier_amount_collision(amount: Optional[float], fields: Dict[str, Any]) -> bool:
    if amount is None:
        return False
    if abs(amount - round(amount)) > 1e-6:
        return False

    amount_digits = str(int(abs(round(amount))))
    if not amount_digits:
        return False

    identifier_keys = ("contract_no", "invoice_no", "tax_no", "bank_account")
    for key in identifier_keys:
        raw = _safe_text((fields or {}).get(key))
        if not raw:
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 6 and digits == amount_digits:
            return True
    return False


def _clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"null", "none", "n/a", "na", "unknown"}:
        return None
    if text in {"\u672a\u77e5", "\u672a\u586b\u5199", "\u65e0", "-", "--"}:
        return None

    text = re.sub(r"^[\s:\uFF1A\-()\[\]\u3010\u3011]+", "", text)
    text = re.sub(r"[\s:\uFF1A\-()\[\]\u3010\u3011]+$", "", text)
    return text or None


def _normalize_date_value(value: Any) -> Optional[str]:
    text = _clean_value(value)
    if not text:
        return None
    normalized = _normalize_date_token(text)
    if normalized:
        return normalized
    date_match = re.search(DATE_PATTERN, text)
    if not date_match:
        return None
    return _normalize_date_token(date_match.group(0))


def _extract_with_llm(raw_text: str, hint_type: Optional[str] = None, llm_backend: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not AUDIT_LLM_ENABLED:
        return None
    if not ask_llm and not get_llm_instance:
        return None

    trimmed = _truncate_text(raw_text or "", AUDIT_LLM_MAX_CHARS)
    if not trimmed:
        return None

    backend = normalize_model_type(llm_backend or AUDIT_LLM_BACKEND)
    doc_types_desc = "\n".join([f"- {key}" for key in AUDIT_DOC_TYPES])
    fields_desc = "\n".join([f"- {key}" for key in AUDIT_FIELD_KEYS])
    hint_note = f"Hint doc_type: {hint_type}" if hint_type else "Hint doc_type: auto"

    system_prompt = (
        "You extract structured audit fields from document text. "
        "Return strict JSON only; no markdown and no explanation."
    )
    prompt = (
        "Extract fields for smart audit from the document text.\n"
        f"Allowed doc_type values:\n{doc_types_desc}\n\n"
        f"Allowed field keys:\n{fields_desc}\n\n"
        "Output requirements:\n"
        "1) Return strict JSON only.\n"
        "2) JSON shape must be {\"doc_type\":\"<type>\",\"fields\":{...}}.\n"
        "3) fields can only contain allowed keys.\n"
        "4) Date fields must be YYYY-MM-DD.\n"
        "5) total_amount must be numeric only and must not be a date/year value.\n"
        "6) If uncertain, return empty string for that field.\n"
        f"{hint_note}\n\n"
        "Document text:\n"
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
        if key in {"total_amount", "exchange_rate", "customs_duty_amount", "vat_amount"}:
            amount = _normalize_amount_value(value)
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


def _post_process_fields(fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    normalized = dict(fields or {})
    text = raw_text or ""
    doc_type = normalize_doc_type(normalized.get("doc_type"))

    for date_key in ("contract_date", "invoice_date", "payment_date"):
        date_val = _normalize_date_value(normalized.get(date_key))
        if date_val:
            normalized[date_key] = date_val
        else:
            normalized.pop(date_key, None)

    amount = _normalize_amount_value(normalized.get("total_amount"))
    keyword_amount = _find_amount_by_keywords(text, AUDIT_AMOUNT_KEYWORDS)
    amount_candidates = _extract_amount_candidates(text)
    if keyword_amount is not None:
        amount = keyword_amount
    elif amount_candidates:
        amount_candidates.sort(key=lambda item: (item[1], item[0], -item[2]), reverse=True)
        amount = amount_candidates[0][0]
    elif amount is not None and not _has_amount_keyword(text):
        # LLM 兜底金额必须有文本语义信号，否则易把合同号/编号误判成金额。
        amount = None

    if _is_identifier_amount_collision(amount, normalized):
        amount = None

    if amount is None:
        normalized.pop("total_amount", None)
    else:
        normalized["total_amount"] = amount

    for numeric_key in ("exchange_rate", "customs_duty_amount", "vat_amount"):
        value = _normalize_amount_value(normalized.get(numeric_key))
        if value is None:
            normalized.pop(numeric_key, None)
        else:
            normalized[numeric_key] = value

    if doc_type == "contract":
        counterparty = _infer_contract_counterparty(text, fallback_vendor=normalized.get("vendor"))
        if counterparty:
            normalized["vendor"] = counterparty
        else:
            current_vendor = _safe_text(normalized.get("vendor"))
            if current_vendor and not _looks_like_org_name(current_vendor):
                normalized.pop("vendor", None)
    return normalized


def _trim_value_by_stop_tokens(value: Any, stop_tokens: List[str]) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    for token in stop_tokens:
        idx = text.find(token)
        if idx > 0:
            text = text[:idx].strip()
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _extract_party_by_labels(text: str, labels: List[str]) -> List[str]:
    source = text or ""
    if not source:
        return []
    stop_tokens = [
        "地址",
        "电话",
        "邮箱",
        "邮编",
        "E-MAIL",
        "EMAIL",
        "TEL",
        "PHONE",
        "ADD:",
        "ADDRESS",
    ]
    values: List[str] = []
    for label in labels:
        pattern = rf"(?:{label})\s*[:：]\s*([^\n\r]{{2,120}})"
        for m in re.finditer(pattern, source, flags=re.IGNORECASE):
            value = _trim_value_by_stop_tokens(m.group(1), stop_tokens)
            if len(value) < 2:
                continue
            if value not in values:
                values.append(value)
    return values


def _looks_like_org_name(name: str) -> bool:
    text = _safe_text(name)
    if len(text) < 2 or len(text) > 80:
        return False
    if re.search(r"[。；;!?！？]", text):
        return False
    upper = text.upper()
    org_tokens = [
        "公司",
        "集团",
        "股份",
        "有限",
        "贸易",
        "实业",
        "工厂",
        "INC",
        "LTD",
        "LLC",
        "CO.",
        "COMPANY",
        "CORP",
        "TRADING",
    ]
    if any(tok in text for tok in org_tokens[:6]) or any(tok in upper for tok in org_tokens[6:]):
        return True
    if re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", text) and len(text) <= 60:
        return True
    return False


def _is_self_org_name(name: str) -> bool:
    candidate = _normalize_text(name)
    if not candidate:
        return False
    for item in AUDIT_SELF_ORG_NAMES:
        normalized = _normalize_text(item)
        if not normalized:
            continue
        if normalized in candidate or candidate in normalized:
            return True
    return False


def _self_org_display_name() -> str:
    for item in AUDIT_SELF_ORG_NAMES:
        text = _safe_text(item)
        if re.search(r"[\u4e00-\u9fff]", text):
            return text
    return _safe_text(AUDIT_SELF_ORG_NAMES[0]) if AUDIT_SELF_ORG_NAMES else ""


def _infer_contract_counterparty(text: str, fallback_vendor: Optional[str] = None) -> str:
    source = text or ""
    if not source:
        return _safe_text(fallback_vendor)

    seller_values = _extract_party_by_labels(source, [r"THE\s+SELLER", r"\bSELLER\b", r"卖方", r"供方", r"乙方"])
    buyer_values = _extract_party_by_labels(source, [r"THE\s+BUYER", r"\bBUYER\b", r"买方", r"需方", r"甲方"])

    sales_hint = _text_contains_any(source, ["销售合同", "销售合同书", "SALES CONTRACT"])
    purchase_hint = _text_contains_any(source, ["采购合同", "PURCHASE CONTRACT"])

    # 合同场景里 vendor 定义为“供应方/卖方”。
    preferred: List[str] = list(seller_values)
    backup: List[str] = list(buyer_values)
    if not preferred and purchase_hint:
        preferred = _extract_party_by_labels(source, [r"乙方", r"供方", r"卖方"])
    if not preferred and sales_hint:
        preferred = _extract_party_by_labels(source, [r"卖方", r"甲方", r"THE\s+SELLER", r"\bSELLER\b"])
    if not backup:
        backup = _extract_party_by_labels(source, [r"买方", r"需方", r"甲方", r"THE\s+BUYER", r"\bBUYER\b"])

    for name in preferred:
        if not _looks_like_org_name(name):
            continue
        if _is_self_org_name(name):
            return _self_org_display_name() or name
        return name
    for name in backup:
        if not _looks_like_org_name(name):
            continue
        if _is_self_org_name(name):
            return _self_org_display_name() or name
        return name

    fallback = _safe_text(fallback_vendor)
    if fallback and _looks_like_org_name(fallback):
        return fallback
    return ""


def _extract_fields(raw_text: str, doc_type: str, llm_backend: Optional[str] = None) -> Dict[str, Any]:
    text = raw_text or ""
    fields: Dict[str, Any] = {"doc_type": doc_type}

    currency = "CNY"
    if "USD" in text or "$" in text:
        currency = "USD"
    elif "EUR" in text or "\u20ac" in text:
        currency = "EUR"
    fields["currency"] = currency

    fields["invoice_no"] = None
    m = re.search(
        r"(?:\u53d1\u7968(?:\u53f7\u7801|\u53f7)?|invoice\s*no\.?)\s*[:\uFF1A]?\s*([A-Za-z0-9\-]{6,30})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["invoice_no"] = m.group(1)

    m = re.search(r"(?:\u7a0e\u53f7|\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7)\s*[:\uFF1A]?\s*([0-9A-Za-z]{12,24})", text)
    if m:
        fields["tax_no"] = m.group(1)

    dates = _extract_dates(text)
    if dates:
        fields["invoice_date"] = dates[0]
        fields["payment_date"] = dates[-1]

    fields["contract_no"] = None
    m = re.search(
        r"(?:\u5408\u540c(?:\u7f16\u53f7|\u53f7)?|\u534f\u8bae(?:\u7f16\u53f7|\u53f7)?)\s*[:\uFF1A]?\s*([A-Za-z0-9\-]{4,40})",
        text,
    )
    if m:
        fields["contract_no"] = m.group(1)

    fields["po_no"] = None
    m = re.search(
        r"\bPO[-_/]?(?=[A-Za-z0-9\-]{3,40}\b)(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9\-]{3,40}\b",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["po_no"] = m.group(0).upper()
    if not fields.get("po_no"):
        m = re.search(
            r"(?:\bPO\b\s*(?:NO\.?|NUMBER|#)?|\u91c7\u8d2d(?:\u5355|\u8ba2\u5355)(?:\u53f7|\u7f16\u53f7)?)\s*[:\uFF1A]?\s*([A-Za-z0-9][A-Za-z0-9\-]{3,40})",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            value = _safe_text(m.group(1))
            if value:
                fields["po_no"] = value

    fields["vendor"] = None
    m = re.search(
        r"(?:\u4f9b\u5e94\u5546|\u9500\u552e\u65b9|\u5356\u65b9|\u4e59\u65b9|\u6536\u6b3e\u65b9)\s*[:\uFF1A]?\s*([^\n\r:]{2,40})",
        text,
    )
    if m:
        fields["vendor"] = m.group(1).strip()

    m = re.search(
        r"(?:\u62a5\u5173(?:\u5355|\u53f7|\u7f16\u53f7)?|declaration\s*no\.?)\s*[:\uFF1A]?\s*([A-Za-z0-9\-]{6,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["declaration_no"] = m.group(1)

    m = re.search(
        r"(?:\u88c5\u7bb1\u5355(?:\u53f7|\u7f16\u53f7)?|packing\s*list(?:\s*no\.?)?)\s*[:\uFF1A]?\s*([A-Za-z0-9\-]{4,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["packing_list_no"] = m.group(1)

    m = re.search(
        r"(?:B\/L|BOL|BL|AWB|bill\s*of\s*lading|air\s*waybill|\u63d0\u5355(?:\u53f7)?|\u8fd0\u5355(?:\u53f7)?)\s*[:\uFF1A#]?\s*([A-Za-z0-9\-]{4,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["bl_awb_no"] = m.group(1)

    m = re.search(
        r"(?:HS\s*CODE|HS\u7f16\u7801|HS\u53f7)\s*[:\uFF1A]?\s*([0-9]{6,12})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["hs_code"] = m.group(1)

    m = re.search(
        r"(?:incoterms?|trade\s*term|\u8d38\u6613\u672f\u8bed)\s*[:\uFF1A]?\s*(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["incoterm"] = m.group(1).upper()

    m = re.search(
        r"(?:country\s*of\s*origin|\u539f\u4ea7\u5730(?:\u56fd)?|\u539f\u4ea7\u56fd)\s*[:\uFF1A]?\s*([A-Za-z\u4e00-\u9fff ]{2,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["origin_country"] = m.group(1).strip()

    m = re.search(
        r"(?:destination\s*country|\u76ee\u7684\u56fd)\s*[:\uFF1A]?\s*([A-Za-z\u4e00-\u9fff ]{2,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["destination_country"] = m.group(1).strip()

    m = re.search(
        r"(?:port\s*of\s*loading|\u8d77\u8fd0\u6e2f|\u88c5\u8fd0\u6e2f)\s*[:\uFF1A]?\s*([A-Za-z\u4e00-\u9fff ]{2,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["port_loading"] = m.group(1).strip()

    m = re.search(
        r"(?:port\s*of\s*discharge|\u76ee\u7684\u6e2f|\u5378\u8d27\u6e2f)\s*[:\uFF1A]?\s*([A-Za-z\u4e00-\u9fff ]{2,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["port_discharge"] = m.group(1).strip()

    m = re.search(
        r"(?:exchange\s*rate|\u6c47\u7387)\s*[:\uFF1A]?\s*([0-9]+(?:\.[0-9]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["exchange_rate"] = _normalize_amount_value(m.group(1))

    m = re.search(
        r"(?:customs\s*duty|\u5173\u7a0e)\s*[:\uFF1A]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["customs_duty_amount"] = _normalize_amount_value(m.group(1))

    m = re.search(
        r"(?:VAT|\u589e\u503c\u7a0e)\s*[:\uFF1A]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        fields["vat_amount"] = _normalize_amount_value(m.group(1))

    total_amount = _find_amount_by_keywords(text, AUDIT_AMOUNT_KEYWORDS)
    if total_amount is None:
        amount_candidates = _extract_amount_candidates(text)
        if amount_candidates:
            amount_candidates.sort(key=lambda item: (item[1], item[0], -item[2]), reverse=True)
            total_amount = amount_candidates[0][0]
        else:
            total_amount = None
    fields["total_amount"] = total_amount

    payee_stop_tokens = [
        "\u4ed8\u6b3e\u65b9\u5f0f",
        "\u7533\u8bf7\u91d1\u989d",
        "\u6536\u6b3e\u94f6\u884c",
        "\u94f6\u884c\u8d26\u53f7",
        "\u9884\u8ba1\u4ed8\u6b3e\u65e5\u671f",
        "\u4ed8\u6b3e\u7c7b\u578b",
        "\u9879\u76ee",
        "\u5907\u6ce8",
        "\u7ecf\u529e\u4eba",
        "\u90e8\u95e8",
        "PAYMENT",
        "BANK",
        "ACCOUNT",
    ]
    m = re.search(
        r"(?:\u6536\s*\u6b3e\s*(?:\u65b9|\u5355\u4f4d|\u8d26\u6237\u540d|\u8d26\s*\u6237\s*\u540d|\u4eba|\u6237\u540d|\u540d\u79f0)|payee|beneficiary)\s*[:\uFF1A]?\s*([^\n\r:\uFF1A]{2,80}?)\s*(?=(?:\u4ed8\u6b3e\u65b9\u5f0f|\u7533\u8bf7\u91d1\u989d|\u6536\u6b3e\u94f6\u884c|\u94f6\u884c\u8d26\u53f7|\u9884\u8ba1\u4ed8\u6b3e\u65e5\u671f|\u4ed8\u6b3e\u7c7b\u578b|\u9879\u76ee|\u5907\u6ce8|\u7ecf\u529e\u4eba|\u90e8\u95e8|$))",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        payee_value = _trim_value_by_stop_tokens(m.group(1), payee_stop_tokens)
        if len(payee_value) >= 2:
            fields["payee"] = payee_value

    m = re.search(
        r"(?:\u94f6\s*\u884c\s*\u8d26\s*\u53f7|\u8d26\s*\u53f7|\u5f00\s*\u6237\s*\u8d26\s*\u53f7|\u6536\s*\u6b3e\s*\u8d26\s*\u53f7)\s*[:\uFF1A]?\s*([0-9\s-]{8,40})",
        text,
    )
    if m:
        fields["bank_account"] = re.sub(r"\s+", "", m.group(1))

    if doc_type == "payment" and not _safe_text(fields.get("payee")) and _safe_text(fields.get("vendor")):
        # 付款单中兜底：未识别收款人时，借助已识别的供应商字段补全。
        fields["payee"] = _safe_text(fields.get("vendor"))

    m = re.search(r"(?:\u62a5\u9500\u4eba|\u7533\u8bf7\u4eba|\u62a5\u9500\u7533\u8bf7\u4eba)\s*[:\uFF1A]?\s*([^\n\r:]{2,20})", text)
    if m:
        fields["reimburser"] = m.group(1).strip()

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

    llm_result = _extract_with_llm(text, doc_type, llm_backend or AUDIT_LLM_BACKEND)
    fields = _merge_llm_fields(fields, llm_result, allow_doc_type_override=False)
    fields = _post_process_fields(fields, text)

    return fields


def _infer_doc_type_llm(raw_text: str, llm_backend: Optional[str] = None) -> Optional[str]:
    llm_result = _extract_with_llm(raw_text or "", None, llm_backend or AUDIT_LLM_BACKEND)
    if not llm_result:
        return None
    doc_type = llm_result.get("doc_type")
    return doc_type if doc_type in AUDIT_DOC_TYPES else None


def _infer_doc_type(raw_text: str) -> str:
    text = raw_text or ""
    lower_text = text.lower()

    payment_form_hits = 0
    payment_form_clues = [
        ["\u9884\u4ed8\u6b3e\u652f\u4ed8\u7533\u8bf7\u5355", "\u4ed8\u6b3e\u7533\u8bf7\u5355", "\u652f\u4ed8\u7533\u8bf7\u5355"],
        ["\u7533\u8bf7\u5355\u7f16\u53f7", "\u4ed8\u6b3e\u7c7b\u578b", "\u652f\u4ed8\u72b6\u6001"],
        ["\u6536\u6b3e\u94f6\u884c", "\u94f6\u884c\u8d26\u53f7", "\u8981\u6c42\u4ed8\u6b3e\u65e5\u671f", "\u9884\u8ba1\u4ed8\u6b3e\u65e5\u671f"],
        ["\u9884\u4ed8\u6b3e\u660e\u7ec6\u4fe1\u606f", "\u652f\u4ed8\u5355\u660e\u7ec6\u4fe1\u606f"],
    ]
    for group in payment_form_clues:
        if _text_contains_any(text, group):
            payment_form_hits += 1
    if payment_form_hits >= 2:
        return "payment"

    # Contract signals come first to avoid采购/销售合同被"发票/提单"类词汇误判.
    if _text_contains_any(
        text,
        [
            "\u9500\u552e\u5408\u540c\u4e66",
            "\u9500\u552e\u5408\u540c",
            "\u91c7\u8d2d\u5408\u540c",
            "\u8d2d\u9500\u5408\u540c",
            "\u5408\u540c\u53f7",
            "\u5408\u540c\u7f16\u53f7",
            "\u5408\u540c\u7b7e\u8ba2",
            "\u5408\u540c\u7b7e\u7f72",
        ],
    ) or _text_contains_any(lower_text, ["sales contract", "purchase contract", "contract no", "cont.no", "the seller", "the buyer"]):
        return "contract"

    if _text_contains_any(text, ["\u62a5\u5173\u5355", "customs declaration", "declaration no"]):
        if _text_contains_any(text, ["\u51fa\u53e3", "export"]):
            return "export_declaration"
        return "import_declaration"

    if _text_contains_any(text, ["\u539f\u4ea7\u5730\u8bc1", "certificate of origin"]):
        return "certificate_of_origin"

    packing_title = _text_contains_any(text, ["packing list", "\u88c5\u7bb1\u5355"])
    packing_structure = _text_contains_any(
        text,
        ["gross weight", "net weight", "measurement", "carton", "\u6bdb\u91cd", "\u51c0\u91cd", "\u4ef6\u6570", "\u7bb1\u6570"],
    )
    if packing_title and packing_structure:
        return "packing_list"

    bill_title = _text_contains_any(text, ["bill of lading", "\u63d0\u5355"])
    bill_structure = _text_contains_any(
        text,
        [
            "shipper",
            "consignee",
            "notify party",
            "vessel",
            "voyage",
            "port of loading",
            "port of discharge",
            "bl no",
            "\u627f\u8fd0\u4eba",
            "\u6258\u8fd0\u4eba",
            "\u6536\u8d27\u4eba",
            "\u901a\u77e5\u4eba",
            "\u8239\u540d",
            "\u822a\u6b21",
            "\u63d0\u5355\u53f7",
        ],
    )
    if bill_title and bill_structure:
        return "bill_of_lading"

    awb_title = _text_contains_any(text, ["air waybill", "airway bill", "\u7a7a\u8fd0\u8fd0\u5355", "\u822a\u7a7a\u8fd0\u5355"])
    awb_structure = _text_contains_any(
        text,
        [
            "mawb",
            "hawb",
            "airport of departure",
            "airport of destination",
            "airline",
            "flight",
            "\u822a\u73ed",
            "\u542f\u8fd0\u673a\u573a",
            "\u76ee\u7684\u5730\u673a\u573a",
            "\u8fd0\u5355\u53f7",
        ],
    )
    if awb_title and awb_structure:
        return "air_waybill"

    invoice_hit = 0
    invoice_clues = [
        ["\u53d1\u7968\u4ee3\u7801", "\u53d1\u7968\u53f7\u7801", "\u6821\u9a8c\u7801", "\u5f00\u7968\u65e5\u671f"],
        ["\u9500\u65b9", "\u8d2d\u65b9", "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7", "\u7a0e\u7387"],
        ["invoice no", "tax invoice", "invoice date"],
    ]
    for group in invoice_clues:
        if _text_contains_any(text, group) or _text_contains_any(lower_text, group):
            invoice_hit += 1

    if invoice_hit >= 2:
        return "invoice"
    if _text_contains_any(text, ["\u53d1\u7968", "\u5f00\u7968", "invoice"]) and not _text_contains_any(text, ["\u5408\u540c", "contract"]):
        return "invoice"

    if _text_contains_any(text, ["\u5408\u540c", "\u534f\u8bae", "\u7b7e\u7f72", "\u7b7e\u8ba2"]) or _text_contains_any(lower_text, ["contract"]):
        return "contract"
    if _text_contains_any(text, ["\u4ed8\u6b3e", "\u6536\u6b3e", "\u94f6\u884c\u8d26\u53f7", "payment"]):
        return "payment"
    if _text_contains_any(text, ["\u62a5\u9500", "\u8d39\u7528", "\u5dee\u65c5", "expense"]):
        return "expense"
    return "invoice"


def _text_contains_any(text: str, keywords: List[str]) -> bool:
    source = text or ""
    if any(kw and kw in source for kw in keywords):
        return True
    normalized_source = _normalize_text(source)
    if not normalized_source:
        return False
    for kw in keywords:
        if not kw:
            continue
        normalized_kw = _normalize_text(kw)
        if normalized_kw and normalized_kw in normalized_source:
            return True
    return False


def _infer_doc_subtype(
    raw_text: str,
    doc_type: str,
    fields: Optional[Dict[str, Any]] = None,
    file_name: Optional[str] = None,
) -> str:
    base_type = normalize_doc_type(doc_type)
    text = raw_text or ""
    file_text = _safe_text(file_name)
    if file_text:
        text = f"{file_text}\n{text}"
    lower_text = text.lower()
    fields = fields or {}
    vendor = _safe_text(fields.get("vendor"))
    contract_no = _safe_text(fields.get("contract_no")).upper()
    po_no = _safe_text(fields.get("po_no")).upper()

    if base_type == "trade_case":
        return "trade_case_generic"

    if base_type == "contract":
        if _text_contains_any(text, ["销售合同", "销货合同", "销售协议"]) or _text_contains_any(lower_text, ["sales contract", "sale contract"]):
            return "sales_contract"
        if _text_contains_any(text, ["采购合同", "购货合同", "采购协议"]) or _text_contains_any(lower_text, ["purchase contract", "procurement contract"]):
            return "purchase_contract"
        if _text_contains_any(text, ["购销合同"]) or _text_contains_any(lower_text, ["sale and purchase contract"]):
            return "sale_purchase_contract"
        if _text_contains_any(text, ["框架合同", "框架协议"]) or _text_contains_any(lower_text, ["framework agreement", "master agreement"]):
            return "framework_contract"
        if _text_contains_any(text, ["服务合同", "技术服务", "咨询服务", "运维服务"]) or _text_contains_any(lower_text, ["service contract", "services agreement"]):
            return "service_contract"
        if _text_contains_any(text, ["劳务合同", "劳务协议"]) or _text_contains_any(lower_text, ["labor contract", "labour contract"]):
            return "labor_contract"
        if _text_contains_any(text, ["租赁合同", "租赁协议"]) or _text_contains_any(lower_text, ["lease agreement", "rental contract"]):
            return "lease_contract"
        if _text_contains_any(text, ["保密协议"]) or _text_contains_any(lower_text, ["nondisclosure agreement", "nda"]):
            return "nda_agreement"

        purchase_role = bool(re.search(r"甲方[^\n\r]{0,24}(?:买方|采购方|需方)", text)) or bool(
            re.search(r"乙方[^\n\r]{0,24}(?:卖方|供方|供应方)", text)
        )
        sales_role = bool(re.search(r"甲方[^\n\r]{0,24}(?:卖方|供方|供应方)", text)) or bool(
            re.search(r"乙方[^\n\r]{0,24}(?:买方|采购方|需方)", text)
        )
        if purchase_role and sales_role:
            return "sale_purchase_contract"
        if purchase_role:
            return "purchase_contract"
        if sales_role:
            return "sales_contract"
        if contract_no.startswith("PO-") or contract_no.startswith("PO"):
            return "purchase_contract"
        if po_no:
            return "purchase_contract"
        if contract_no.startswith("SO-") or contract_no.startswith("SO"):
            return "sales_contract"
        return "contract_generic"

    if base_type == "invoice":
        if _text_contains_any(text, ["增值税专用发票", "专票"]) or _text_contains_any(lower_text, ["vat special invoice"]):
            return "vat_special_invoice"
        if _text_contains_any(text, ["增值税普通发票", "普票"]) or _text_contains_any(lower_text, ["vat invoice", "vat general invoice"]):
            return "vat_general_invoice"
        if _text_contains_any(text, ["形式发票"]) or _text_contains_any(lower_text, ["proforma invoice", "pro forma invoice"]):
            return "proforma_invoice"
        if _text_contains_any(text, ["销项发票", "销售发票", "开票方"]) or _text_contains_any(lower_text, ["sales invoice", "output invoice"]):
            return "sales_invoice"
        if _text_contains_any(text, ["进项发票", "采购发票", "受票方"]) or _text_contains_any(lower_text, ["purchase invoice", "input invoice"]):
            return "purchase_invoice"
        if vendor and _text_contains_any(text, ["购买方", "购方"]):
            return "purchase_invoice"
        return "invoice_generic"

    if base_type == "import_declaration":
        return "import_customs_declaration"

    if base_type == "export_declaration":
        return "export_customs_declaration"

    if base_type == "packing_list":
        if _text_contains_any(text, ["出口", "出境"]) or _text_contains_any(lower_text, ["export"]):
            return "export_packing_list"
        if _text_contains_any(text, ["进口", "入境"]) or _text_contains_any(lower_text, ["import"]):
            return "import_packing_list"
        return "packing_list_generic"

    if base_type == "bill_of_lading":
        if _text_contains_any(text, ["主提单"]) or _text_contains_any(lower_text, ["master bill of lading", "mbl"]):
            return "master_bill_of_lading"
        if _text_contains_any(text, ["分提单"]) or _text_contains_any(lower_text, ["house bill of lading", "hbl"]):
            return "house_bill_of_lading"
        if _text_contains_any(text, ["海运", "船名"]) or _text_contains_any(lower_text, ["ocean bill of lading", "vessel"]):
            return "ocean_bill_of_lading"
        return "bill_of_lading_generic"

    if base_type == "air_waybill":
        if _text_contains_any(text, ["主运单"]) or _text_contains_any(lower_text, ["master air waybill", "mawb"]):
            return "master_air_waybill"
        if _text_contains_any(text, ["分运单"]) or _text_contains_any(lower_text, ["house air waybill", "hawb"]):
            return "house_air_waybill"
        return "air_waybill_generic"

    if base_type == "certificate_of_origin":
        if _text_contains_any(lower_text, ["form e"]):
            return "coo_form_e"
        if _text_contains_any(lower_text, ["form a"]):
            return "coo_form_a"
        return "certificate_of_origin_generic"

    if base_type == "payment":
        if _text_contains_any(text, ["预付款", "定金"]) or _text_contains_any(lower_text, ["advance payment", "down payment"]):
            return "advance_payment"
        if _text_contains_any(text, ["尾款", "余款"]) or _text_contains_any(lower_text, ["final payment", "balance payment"]):
            return "final_payment"
        return "payment_generic"

    if base_type == "expense":
        if _text_contains_any(text, ["差旅", "机票", "酒店"]) or _text_contains_any(lower_text, ["travel expense", "business trip"]):
            return "travel_expense"
        if _text_contains_any(text, ["推广", "投放", "市场活动"]) or _text_contains_any(lower_text, ["marketing expense"]):
            return "marketing_expense"
        return "expense_generic"

    return ""


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
        "reason": _safe_text(reason) or _safe_text(message) or "命中风险规则",
        "suggestion": _safe_text(suggestion) or "建议人工复核",
        "action": _safe_text(action) or _safe_text(suggestion) or "建议人工复核",
        "evidence": evidence or None,
        "confidence": score,
    }


def _condition_to_text(cond: Dict[str, Any]) -> str:
    field = _safe_text(cond.get("field") or "field")
    op = _safe_text(cond.get("op") or "exists")
    value = cond.get("value_field") if cond.get("value_field") is not None else cond.get("value")
    op_map = {
        "exists": "exists",
        "missing": "missing",
        "missing_or_zero": "missing_or_zero",
        "eq": "==",
        "neq": "!=",
        "contains": "contains",
        "not_contains": "not_contains",
        "regex": "regex",
        "in": "in",
        "not_in": "not_in",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "gt_field": "> field",
        "lt_field": "< field",
        "truthy": "truthy",
        "falsy": "falsy",
    }
    desc = op_map.get(op, op)
    if value is None or value == "":
        return f"{field} {desc}"
    return f"{field} {desc} {value}"


def _build_rule_reason(rule: Dict[str, Any], checks: List[Dict[str, Any]]) -> str:
    rule_id = _safe_text(rule.get("id") or "RULE")
    if checks:
        return f"规则 {rule_id} 命中：{'; '.join(_condition_to_text(c) for c in checks[:3])}"
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

        if when and not all(_check_condition(cond, ctx) for cond in when):
            continue

        failed = False
        if checks:
            for cond in checks:
                if _check_condition(cond, ctx):
                    failed = True
                    break
        else:
            failed = True

        if not failed:
            continue

        reason = _safe_text(rule.get("reason")) or _build_rule_reason(rule, checks)
        suggestion = _safe_text(rule.get("suggestion")) or "建议人工复核"
        findings.append(
            _build_finding(
                source="rule",
                decision_mode="rule_hit",
                finding_type="policy",
                severity=rule.get("severity", "medium"),
                message=_safe_text(rule.get("message") or "命中规则"),
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
            top_msg = _safe_text(findings[0].get("message")) if findings else "无风险提示信息"

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
        return "No historical review feedback yet."

    lines = [
        f"Historical reviews: {reviewed}",
        f"Approved: {int(feedback_ctx.get('approved_count') or 0)}",
        f"Rejected: {int(feedback_ctx.get('rejected_count') or 0)}",
        f"Need more info: {int(feedback_ctx.get('need_more_count') or 0)}",
    ]
    fp_hints = feedback_ctx.get("false_positive_hints") or []
    fn_hints = feedback_ctx.get("false_negative_hints") or []
    notes = feedback_ctx.get("review_notes") or []

    if fp_hints:
        lines.append(f"Possible false-positive patterns: {fp_hints}")
    if fn_hints:
        lines.append(f"Possible false-negative patterns: {fn_hints}")
    if notes:
        lines.append(f"Recent reviewer notes: {notes}")

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
        suggestion = _safe_text(item.get("suggestion") or "Need manual review")
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
你是企业智能审单助手。请基于提取字段与风险信号输出严格 JSON，不要输出 markdown 或额外说明。

硬约束：
1) 不要把日期当成金额。
2) total_amount 必须是纯数字（不能带年份/日期片段，不能带货币符号）。
3) 日期字段必须是 YYYY-MM-DD。
4) findings 要简洁、可核验、有证据。
5) 如果 high_risk_rule 为 true，除非证据充分，否则 pass 必须为 false。
6) summary、message、reason、suggestion、action 必须使用简体中文（保留编号/金额等原始值）。

单据类型：{doc_type}
是否命中高风险规则：{high_risk_rule}

提取字段：
{json.dumps(fields, ensure_ascii=False)}

确定性规则结果：
{json.dumps(rule_signals, ensure_ascii=False)}

ERP 上下文：
{json.dumps(erp_digest, ensure_ascii=False)}

异常统计：
{json.dumps(anomaly_stats or {}, ensure_ascii=False)}

历史复核摘要：
{_feedback_prompt(feedback_ctx)}

原文（截断）：
{_truncate_text(raw_text)}

输出 JSON 结构：
{{
  "risk_level": "low|medium|high",
  "pass": true/false,
  "summary": "...",
  "findings": [
    {{
      "type": "semantic|cross_doc|policy|anomaly",
      "severity": "low|medium|high",
      "message": "...",
      "reason": "...",
      "suggestion": "...",
      "action": "...",
      "confidence": 0.0,
      "decision_mode": "ai_semantic",
      "evidence": {{"text": "...", "highlight": "..."}}
    }}
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
    current_date = _parse_date(
        fields.get("payment_date") or fields.get("invoice_date") or fields.get("contract_date")
    ) or datetime.utcnow()

    def _amounts(filter_fn) -> List[float]:
        values: List[float] = []
        for rec in history_records or []:
            if not filter_fn(rec):
                continue
            rec_amount = _safe_float((rec.get("fields") or {}).get("total_amount"))
            if rec_amount is not None:
                values.append(rec_amount)
        return values

    def _detect_zscore(
        group_key: str,
        group_name: str,
        values: List[float],
        severity_base: str = "medium",
    ) -> None:
        if len(values) < ANOMALY_MIN_SAMPLES:
            return
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
        std = variance ** 0.5
        if std <= 1e-6:
            return

        zscore = (amount - mean) / std
        stats[f"{group_key}_samples"] = len(values)
        stats[f"{group_key}_mean"] = round(mean, 4)
        stats[f"{group_key}_std"] = round(std, 4)
        stats[f"{group_key}_zscore"] = round(zscore, 4)

        if abs(zscore) < 2.5:
            return

        severity = "high" if abs(zscore) >= 3.5 else severity_base
        confidence = _clamp(0.70 + min(abs(zscore), 6.0) / 10.0, 0.70, 0.99)
        findings.append(
            _build_finding(
                source="anomaly",
                decision_mode="anomaly_detection",
                finding_type=f"{group_key}_amount_anomaly",
                severity=severity,
                message=f"{group_name}金额异常",
                reason=f"当前金额 {amount:.2f} 与历史均值 {mean:.2f} 偏差较大（z={zscore:.2f}）。",
                suggestion="建议人工复核业务合理性与原始凭证。",
                action="建议人工复核",
                evidence={
                    "text": f"amount={amount:.2f}, mean={mean:.2f}, std={std:.2f}",
                    "highlight": f"z={zscore:.2f}",
                },
                confidence=confidence,
            )
        )

    same_vendor_amounts = _amounts(
        lambda rec: _normalize_text((rec.get("fields") or {}).get("vendor") or (rec.get("fields") or {}).get("payee"))
        == _normalize_text(vendor) if vendor else False
    )
    same_reimburser_amounts = _amounts(
        lambda rec: _normalize_text((rec.get("fields") or {}).get("reimburser")) == _normalize_text(reimburser)
        if reimburser else False
    )
    same_doc_type_amounts = _amounts(lambda rec: _safe_text(rec.get("doc_type")).lower() == _safe_text(doc_type).lower())

    _detect_zscore("same_vendor", "同供应商", same_vendor_amounts, severity_base="medium")
    _detect_zscore("same_reimburser", "同报销人", same_reimburser_amounts, severity_base="medium")
    _detect_zscore("same_doc_type", "同类型单据", same_doc_type_amounts, severity_base="low")

    duplicate_invoice_count = 0
    if invoice_no:
        duplicate_invoice = [
            rec for rec in (history_records or [])
            if _normalize_text((rec.get("fields") or {}).get("invoice_no")) == _normalize_text(invoice_no)
        ]
        duplicate_invoice_count = len(duplicate_invoice)
        if duplicate_invoice_count > 0:
            findings.append(
                _build_finding(
                    source="anomaly",
                    decision_mode="anomaly_detection",
                    finding_type="duplicate_invoice",
                    severity="high",
                    message="疑似重复发票",
                    reason=f"发票号 {invoice_no} 在历史记录中出现 {duplicate_invoice_count} 次。",
                    suggestion="建议中止处理并核验是否重复报销。",
                    action="建议驳回并核查",
                    evidence={"text": invoice_no, "highlight": invoice_no},
                    confidence=0.99,
                )
            )
    stats["duplicate_invoice_count"] = duplicate_invoice_count

    duplicate_reimbursement_count = 0
    for rec in history_records or []:
        rec_fields = rec.get("fields") or {}
        rec_reimburser = _safe_text(rec_fields.get("reimburser"))
        rec_amount = _safe_float(rec_fields.get("total_amount"))
        if not reimburser or _normalize_text(rec_reimburser) != _normalize_text(reimburser) or rec_amount is None:
            continue
        if abs(rec_amount - amount) > 0.01:
            continue
        rec_date = _parse_date(rec_fields.get("payment_date") or rec_fields.get("invoice_date") or rec.get("created_at"))
        if not rec_date:
            continue
        if abs((current_date - rec_date).days) <= 45:
            duplicate_reimbursement_count += 1

    stats["duplicate_reimbursement_count"] = duplicate_reimbursement_count
    if duplicate_reimbursement_count > 0:
        findings.append(
            _build_finding(
                source="anomaly",
                decision_mode="anomaly_detection",
                finding_type="duplicate_reimbursement_window",
                severity="high",
                message="短周期重复报销风险",
                reason=(
                    f"报销人 {reimburser or '未知'} 在 45 天内出现 {duplicate_reimbursement_count} 次同金额记录。"
                ),
                suggestion="建议核验是否重复提交，并转人工审批。",
                action="建议驳回并核查",
                evidence={"text": f"{reimburser or '未知'} / {amount:.2f}", "highlight": f"{amount:.2f}"},
                confidence=0.98,
            )
        )

    return findings[:AI_MAX_FINDINGS], stats


def _run_cross_document_checks(
    doc_type: str,
    fields: Dict[str, Any],
    erp_ctx: Dict[str, Any],
    history_records: List[Dict[str, Any]],
    case_documents: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []
    case_documents = case_documents or []

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

    def _add_check(
        check_id: str,
        name: str,
        passed: bool,
        reason: str,
        severity: str = "medium",
        suggestion: str = "请复核并核验原始单据",
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

    case_has_contract = any(
        _safe_text(item.get("tag")).lower() == "contract" or normalize_doc_type(item.get("doc_type")) == "contract"
        for item in case_documents
        if isinstance(item, dict)
    )
    history_has_contract = any(
        _safe_text(rec.get("doc_type")).lower() == "contract"
        for rec in (history_records or [])
    )
    if doc_type != "contract":
        has_contract_baseline = case_has_contract or history_has_contract
        _add_check(
            "contract_baseline",
            "合同基线完整性校验",
            has_contract_baseline,
            "已找到合同主文档，可进行跨单据比对" if has_contract_baseline else "缺少合同主文档，暂无法进行有效比对",
            severity="high",
            suggestion="请先上传合同后再上传发票/提单/装箱单/付款单。",
            confidence=0.99,
            actual="已找到合同" if has_contract_baseline else "未找到合同",
            expected="合同主文档已上传",
            evidence={"text": contract_no or "未提供合同号", "highlight": contract_no or "合同"},
        )
        if not has_contract_baseline:
            return findings[:AI_MAX_FINDINGS], checks

    _add_check(
        "vendor_blacklist",
        "供应商黑名单校验",
        not blacklist_hit,
        "供应商命中黑名单" if blacklist_hit else "供应商未命中黑名单",
        severity="high",
        suggestion="建议拦截付款并升级至合规复核",
        confidence=0.99,
        actual=blacklist_hit,
        expected=False,
        evidence={"text": expected_vendor or vendor, "highlight": expected_vendor or vendor},
    )

    if vendor_status:
        blocked_status = {"blacklist", "suspended", "inactive", "blocked"}
        is_valid_status = vendor_status not in blocked_status
        vendor_status_map = {
            "unknown": "未知",
            "active": "正常",
            "blacklist": "黑名单",
            "suspended": "停用",
            "inactive": "未激活",
            "blocked": "冻结",
        }
        vendor_status_text = vendor_status_map.get(vendor_status, vendor_status)
        _add_check(
            "vendor_status",
            "供应商状态校验",
            is_valid_status,
            f"供应商状态为：{vendor_status_text}",
            severity="high" if not is_valid_status else "low",
            suggestion="建议核验供应商主数据与审批流程",
            confidence=0.95,
            actual=vendor_status_text,
            expected="正常",
            evidence={"text": vendor_status_text, "highlight": vendor_status_text},
        )

    if expected_vendor and vendor:
        matched = _normalize_text(expected_vendor) == _normalize_text(vendor)
        _add_check(
            "vendor_match",
            "供应商一致性校验",
            matched,
            "供应商与ERP主数据一致" if matched else "供应商与ERP主数据不一致",
            severity="high",
            suggestion="建议付款前核对合同与供应商映射关系",
            confidence=0.96,
            actual=vendor,
            expected=expected_vendor,
            evidence={"text": vendor, "highlight": vendor},
        )

    if amount is not None and contract_amount is not None and contract_amount > 0:
        limit = contract_amount * 1.05
        within_contract = amount <= limit
        _add_check(
            "amount_vs_contract",
            "金额-合同上限校验",
            within_contract,
            f"金额 {amount:.2f} 超过合同上限 {limit:.2f}" if not within_contract else "金额在合同上限内",
            severity="high",
            suggestion="建议核验变更单或调整金额后再提交",
            confidence=0.95,
            actual=amount,
            expected=limit,
            evidence={"text": str(amount), "highlight": str(amount)},
        )

    if amount is not None and po_amount is not None and po_amount > 0:
        po_limit = po_amount * 1.05
        within_po = amount <= po_limit
        _add_check(
            "amount_vs_po",
            "金额-采购单上限校验",
            within_po,
            f"金额 {amount:.2f} 超过采购单上限 {po_limit:.2f}" if not within_po else "金额在采购单上限内",
            severity="medium",
            suggestion="建议核对采购单变更后再处理",
            confidence=0.93,
            actual=amount,
            expected=po_limit,
            evidence={"text": str(amount), "highlight": str(amount)},
        )

    if amount is not None and budget_remaining is not None:
        within_budget = amount <= budget_remaining
        _add_check(
            "budget_remaining",
            "预算余额校验",
            within_budget,
            f"金额 {amount:.2f} 超过预算余额 {budget_remaining:.2f}" if not within_budget else "金额在预算余额内",
            severity="high",
            suggestion="建议先申请预算审批再付款",
            confidence=0.94,
            actual=amount,
            expected=budget_remaining,
            evidence={"text": str(amount), "highlight": str(amount)},
        )

    if invoice_no:
        duplicate_hits = []
        for rec in history_records or []:
            rec_fields = rec.get("fields") or {}
            rec_invoice = _safe_text(rec_fields.get("invoice_no"))
            rec_amount = _safe_float(rec_fields.get("total_amount"))
            if rec_invoice and _normalize_text(rec_invoice) == _normalize_text(invoice_no):
                duplicate_hits.append({
                    "job_id": rec.get("job_id"),
                    "amount": rec_amount,
                    "doc_type": rec.get("doc_type"),
                })
        _add_check(
            "duplicate_invoice_no",
            "发票号重复校验",
            len(duplicate_hits) == 0,
            "发现重复发票号" if duplicate_hits else "历史中未发现重复发票号",
            severity="high",
            suggestion="建议中止处理并核验是否重复报销",
            confidence=0.98,
            actual=invoice_no,
            expected="唯一",
            evidence={"text": invoice_no, "highlight": invoice_no, "matches": duplicate_hits[:5]},
        )

    if payment_date and invoice_date:
        paid_after_invoice = payment_date >= invoice_date
        _add_check(
            "payment_after_invoice",
            "付款日期顺序校验",
            paid_after_invoice,
            "付款日期早于发票日期" if not paid_after_invoice else "付款日期顺序正常",
            severity="medium",
            suggestion="建议复核发票开具日期与付款申请日期",
            confidence=0.9,
            actual=payment_date.isoformat(),
            expected=invoice_date.isoformat(),
            evidence={"text": f"{payment_date} / {invoice_date}", "highlight": str(payment_date)},
        )

    if invoice_date and contract_date:
        invoice_after_contract = invoice_date >= contract_date
        _add_check(
            "invoice_after_contract",
            "发票-合同日期顺序校验",
            invoice_after_contract,
            "发票日期早于合同日期" if not invoice_after_contract else "发票日期与合同日期顺序正常",
            severity="medium",
            suggestion="建议核验合同元数据与发票有效性",
            confidence=0.9,
            actual=invoice_date.isoformat(),
            expected=contract_date.isoformat(),
            evidence={"text": f"{invoice_date} / {contract_date}", "highlight": str(invoice_date)},
        )

    if doc_type in {"payment", "expense"} and amount is not None and contract_amount is not None and contract_amount > 0:
        projected_paid = paid_amount + amount
        over_paid = projected_paid > contract_amount * 1.05
        _add_check(
            "cumulative_paid_over_contract",
            "累计付款金额校验",
            not over_paid,
            f"预计累计付款 {projected_paid:.2f} 超过合同金额 {contract_amount:.2f}" if over_paid else "预计累计付款未超过合同金额",
            severity="high",
            suggestion="建议冻结付款并核查超付风险",
            confidence=0.97,
            actual=projected_paid,
            expected=contract_amount,
            evidence={"text": str(projected_paid), "highlight": str(projected_paid)},
        )

    if contract_no and amount is not None:
        same_contract_paid = 0.0
        for rec in history_records or []:
            rec_fields = rec.get("fields") or {}
            rec_contract = _safe_text(rec_fields.get("contract_no"))
            rec_amount = _safe_float(rec_fields.get("total_amount"))
            rec_doc_type = _safe_text(rec.get("doc_type")).lower()
            if rec_contract and _normalize_text(rec_contract) == _normalize_text(contract_no):
                if rec_doc_type in {"payment", "expense"} and rec_amount is not None:
                    same_contract_paid += rec_amount
        if same_contract_paid > 0 and contract_amount is not None and contract_amount > 0:
            projected = same_contract_paid + amount
            over_contract = projected > contract_amount * 1.05
            _add_check(
                "same_contract_cumulative",
                "同合同累计金额校验",
                not over_contract,
                f"历史+当前金额 {projected:.2f} 超过合同金额 {contract_amount:.2f}" if over_contract else "历史+当前金额未超过合同金额",
                severity="high",
                suggestion="建议复核同合同结算计划",
                confidence=0.95,
                actual=projected,
                expected=contract_amount,
                evidence={"text": contract_no, "highlight": contract_no},
            )

    return findings[:AI_MAX_FINDINGS], checks


def _has_high_risk(findings: List[Dict[str, Any]]) -> bool:
    return any(_normalize_severity(item.get("severity"), default="low") == "high" for item in (findings or []))


def _risk_level(findings: List[Dict[str, Any]]) -> str:
    severities = [_normalize_severity(f.get("severity"), default="low") for f in findings]
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _build_summary(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "未发现显著风险。"

    counts = Counter(_normalize_severity(f.get("severity"), default="low") for f in findings)
    top_messages: List[str] = []
    for item in findings[:3]:
        msg = _safe_text(item.get("message"))
        if msg:
            top_messages.append(msg)

    severity_part = (
        f"高风险: {counts.get('high', 0)}，"
        f"中风险: {counts.get('medium', 0)}，"
        f"低风险: {counts.get('low', 0)}"
    )
    message_part = "；".join(top_messages) if top_messages else "关键问题建议人工复核。"
    return f"共识别 {len(findings)} 项风险（{severity_part}）。重点问题：{message_part}"


def _has_chinese_text(text: Any) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", _safe_text(text)))


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
    ai_assessment = ai_assessment or {}
    feedback_ctx = feedback_ctx or {}
    return [
        {
            "step": "extract_fields",
            "detail": "已完成字段抽取与规范化。",
            "doc_type": doc_type,
            "fields_count": len(fields.keys()),
            "at": _now_iso(),
        },
        {
            "step": "rule_engine",
            "detail": f"规则引擎识别 {len(rule_findings)} 项风险。",
            "hits": len(rule_findings),
            "high_risk_hits": sum(1 for f in rule_findings if _normalize_severity(f.get("severity")) == "high"),
            "at": _now_iso(),
        },
        {
            "step": "cross_doc_reconciliation",
            "detail": f"跨单据核对识别 {len(cross_findings)} 项风险。",
            "hits": len(cross_findings),
            "erp_provider": erp_ctx.get("provider"),
            "at": _now_iso(),
        },
        {
            "step": "anomaly_detection",
            "detail": f"异常检测识别 {len(anomaly_findings)} 项风险。",
            "hits": len(anomaly_findings),
            "at": _now_iso(),
        },
        {
            "step": "ai_semantic_review",
            "detail": "AI 语义审查已完成。",
            "risk_level": ai_assessment.get("risk_level"),
            "confidence": ai_assessment.get("confidence"),
            "feedback_reviewed": feedback_ctx.get("reviewed_count", 0),
            "at": _now_iso(),
        },
        {
            "step": "final_decision",
            "detail": "已汇总全部检查并生成最终结论。",
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
    job_snapshot: Optional[Dict[str, Any]] = None
    with AUDIT_LOCK:
        job = AUDIT_JOBS.get(job_id)
        if not job:
            job = _load_job_state(job_id) or _load_job_from_db(job_id)
            if job:
                AUDIT_JOBS[job_id] = job
        if not job:
            return
        job["result"] = result
        job["updated_at"] = _now_iso()
        job_snapshot = dict(job)
    if job_snapshot:
        _persist_job_state(job_snapshot)


def _queue_erp_sync_task(
    *,
    job_id: str,
    user_id: str,
    action: str,
    operator_id: str,
    comment: Optional[str],
    provider: str,
    result: Dict[str, Any],
    last_error: Optional[str] = None,
) -> Dict[str, Any]:
    queue_id = str(uuid.uuid4())
    now = _now_iso()
    task = {
        "queue_id": queue_id,
        "job_id": job_id,
        "user_id": user_id or "anonymous",
        "provider": provider,
        "action": action,
        "operator_id": operator_id or "system",
        "comment": comment,
        "status": "queued",
        "retry_count": 0,
        "max_retry": ERP_SYNC_MAX_RETRY,
        "last_error": last_error,
        "created_at": now,
        "updated_at": now,
        "payload": {
            "risk_level": result.get("risk_level"),
            "audit_score": result.get("audit_score"),
        },
    }
    with ERP_SYNC_LOCK:
        ERP_SYNC_QUEUE[queue_id] = task
    _persist_erp_queue_state(task)
    return task


def _sync_erp_action_direct(
    *,
    job_id: str,
    user_id: str,
    action: str,
    operator_id: str,
    result: Dict[str, Any],
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    if not callable(get_erp_adapter):
        raise RuntimeError("ERP adapter unavailable")
    adapter = get_erp_adapter(ERP_PROVIDER, user_id=user_id)
    return adapter.writeback_audit_action(
        job_id=job_id,
        action=action,
        operator_id=operator_id or "system",
        result=result,
        comment=comment,
    )


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
    sync_payload: Dict[str, Any] = {}
    queue_task: Optional[Dict[str, Any]] = None
    sync_error: Optional[str] = None

    # queue 模式用于“先保留 ERP 接口语义，后接真实 ERP”。
    if AUDIT_ERP_SYNC_MODE == "direct":
        try:
            sync_payload = _sync_erp_action_direct(
                job_id=job_id,
                user_id=user_id,
                action=action_norm,
                operator_id=operator_id or "system",
                result=result,
                comment=comment,
            )
        except Exception as e:
            sync_error = str(e)
            queue_task = _queue_erp_sync_task(
                job_id=job_id,
                user_id=user_id,
                action=action_norm,
                operator_id=operator_id or "system",
                comment=comment,
                provider=ERP_PROVIDER,
                result=result,
                last_error=sync_error,
            )
            sync_payload = {
                "trace_id": f"ERPQ-{queue_task['queue_id'][:8]}",
                "provider": ERP_PROVIDER,
                "status": "queued",
                "stored": False,
                "queue_id": queue_task["queue_id"],
            }
    else:
        queue_task = _queue_erp_sync_task(
            job_id=job_id,
            user_id=user_id,
            action=action_norm,
            operator_id=operator_id or "system",
            comment=comment,
            provider=ERP_PROVIDER,
            result=result,
        )
        sync_payload = {
            "trace_id": f"ERPQ-{queue_task['queue_id'][:8]}",
            "provider": ERP_PROVIDER,
            "status": "queued",
            "stored": False,
            "queue_id": queue_task["queue_id"],
        }

    erp_action = {
        "action": action_norm,
        "operator_id": operator_id or "system",
        "comment": comment,
        "trace_id": sync_payload.get("trace_id"),
        "provider": sync_payload.get("provider"),
        "status": sync_payload.get("status"),
        "stored": sync_payload.get("stored"),
        "queue_id": sync_payload.get("queue_id"),
        "sync_error": sync_error,
        "at": _now_iso(),
    }
    result["erp_action"] = erp_action
    result["erp_trace_id"] = sync_payload.get("trace_id")
    result["erp_sync_status"] = sync_payload.get("status")
    decision_trace = result.get("decision_trace") if isinstance(result.get("decision_trace"), list) else []
    decision_trace.append(
        {
            "step": "erp_writeback",
            "detail": "审单动作已同步至 ERP 适配层。",
            "action": action_norm,
            "trace_id": sync_payload.get("trace_id"),
            "provider": sync_payload.get("provider"),
            "status": sync_payload.get("status"),
            "queue_id": sync_payload.get("queue_id"),
            "at": _now_iso(),
        }
    )
    result["decision_trace"] = decision_trace

    _persist_audit_result(job_id, result)
    _update_job_result_in_memory(job_id, result)
    _update_db(
        "audit_jobs",
        {
            "updated_at": _now_iso(),
            "stage": "erp_pending_sync" if sync_payload.get("status") == "queued" else "done",
        },
        job_id,
    )
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


def _extract_text(file_bytes: bytes, filename: str) -> Tuple[str, List[str], Optional[float], str]:
    ext = os.path.splitext(filename)[1].lower()

    # 审单场景：PDF/Word 始终优先走文本解析链路，不进入 OCR。
    if ext in {".pdf", ".doc", ".docx"}:
        raw_text, page_texts = _parse_with_loader(file_bytes, filename)
        if raw_text:
            if ext == ".pdf":
                mode = "loader_pdf_fast" if (
                    AUDIT_PDF_FAST_PARSE_ENABLED
                    and len((raw_text or "").strip()) >= AUDIT_PDF_FAST_PARSE_MIN_CHARS
                ) else "loader_pdf_direct"
                return raw_text, page_texts, None, mode
            if ext in {".doc", ".docx"}:
                return raw_text, page_texts, None, "loader_word_direct"
            return raw_text, page_texts, None, "loader_direct"
        if ext == ".pdf":
            return "", page_texts, None, "loader_pdf_empty"
        return "", page_texts, None, "loader_word_empty"

    if ext in OCR_REQUIRED_EXTENSIONS:
        try:
            raw_text, page_texts, confidence = _parse_with_ocr(file_bytes, filename)
            return raw_text, page_texts, confidence, "ocr"
        except Exception:
            # 图像类文件以 OCR 为主路径。
            raise

    if ext in DIRECT_PARSE_EXTENSIONS:
        raw_text, page_texts = _parse_with_loader(file_bytes, filename)
        if raw_text:
            return raw_text, page_texts, None, "loader"
        if ext == ".txt":
            try:
                raw_text = file_bytes.decode("utf-8", errors="ignore").strip()
                return raw_text, [], None, "text_decode_fallback"
            except Exception:
                return "", [], None, "empty"
        return "", page_texts, None, "loader_empty"

    try:
        raw_text = file_bytes.decode("utf-8", errors="ignore").strip()
        return raw_text, [], None, "text_decode"
    except Exception:
        return "", [], None, "empty"


def run_audit_job_from_job_id(
    job_id: str,
    model_type: Optional[str] = None,
    case_id: Optional[str] = None,
) -> None:
    local_job = dict(_hydrate_job_from_storage(job_id) or {})

    job = _load_job_from_db(job_id)
    if job and local_job.get("model_type"):
        job["model_type"] = local_job.get("model_type")
    if job and local_job.get("local_path"):
        job["local_path"] = local_job.get("local_path")
    if not job:
        job = local_job
    if not job:
        raise RuntimeError(f"Audit job not found: {job_id}")

    file_url = job.get("file_url")
    if not file_url:
        raise RuntimeError(f"Audit job missing file path: {job_id}")

    local_path = _resolve_audit_local_path(
        file_url,
        user_id=job.get("user_id"),
        job_id=job_id,
        file_name=job.get("file_name"),
        local_path_hint=job.get("local_path"),
    )
    if not local_path or not os.path.exists(local_path):
        raise FileNotFoundError(f"Audit file not found: {local_path}")

    with open(local_path, "rb") as f:
        file_bytes = f.read()

    filename = job.get("file_name") or os.path.basename(local_path) or "document"
    user_id = job.get("user_id") or "anonymous"
    doc_type = job.get("doc_type") or "auto"
    selected_model = normalize_model_type(model_type or job.get("model_type"))
    effective_case_id = _normalize_case_id(case_id) or _normalize_case_id(job.get("case_id"))
    run_audit_job(
        job_id,
        file_bytes,
        filename,
        user_id,
        doc_type,
        case_id=effective_case_id,
        file_url=file_url,
        model_type=selected_model,
    )


def _run_audit_job_inline_async(
    job_id: str,
    model_type: Optional[str] = None,
    case_id: Optional[str] = None,
) -> None:
    """Fallback path when Redis/RQ is unavailable."""
    def _target() -> None:
        try:
            run_audit_job_from_job_id(job_id, model_type=model_type, case_id=case_id)
        except Exception as e:
            snapshot = _hydrate_job_from_storage(job_id) or _load_job_from_db(job_id) or {}
            effective_case_id = _normalize_case_id(case_id) or _normalize_case_id(snapshot.get("case_id"))
            update_job(
                job_id,
                status="failed",
                progress=STAGE_PROGRESS["failed"],
                stage="failed",
                workflow_state="failed",
                error_message=str(e),
            )
            _update_case_document_entry(case_id=effective_case_id, job_id=job_id, status="failed")
            print(f"[Audit Queue Fallback] job {job_id} failed: {e}")

    thread = threading.Thread(
        target=_target,
        name=f"audit-inline-{job_id[:8]}",
        daemon=True,
    )
    thread.start()


def enqueue_audit_job(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    doc_type: Optional[str],
    case_id: Optional[str] = None,
    model_type: Optional[str] = None,
) -> Dict[str, Any]:
    selected_model = normalize_model_type(model_type)
    job = create_job(file_bytes, filename, user_id, doc_type, case_id=case_id, model_type=selected_model)
    queue_job_id = f"audit:{job['job_id']}"

    if enqueue_job is None:
        if not AUDIT_INLINE_FALLBACK:
            raise RuntimeError("Audit queue is unavailable, check Redis/RQ dependencies")
        print("[Audit Queue] RQ unavailable, fallback to inline worker thread")
        _run_audit_job_inline_async(job["job_id"], model_type=selected_model, case_id=job.get("case_id"))
        return job

    try:
        enqueue_job(
            queue_name=AUDIT_QUEUE_NAME,
            func=run_audit_job_from_job_id,
            kwargs={"job_id": job["job_id"], "model_type": selected_model, "case_id": job.get("case_id")},
            job_id=queue_job_id,
            retry_max=AUDIT_JOB_RETRY_MAX,
            timeout=AUDIT_JOB_TIMEOUT_SECONDS,
        )
    except Exception as e:
        if AUDIT_INLINE_FALLBACK:
            print(f"[Audit Queue] enqueue failed ({e}), fallback to inline worker thread")
            _run_audit_job_inline_async(job["job_id"], model_type=selected_model, case_id=job.get("case_id"))
            return job
        update_job(
            job["job_id"],
            status="failed",
            stage="failed",
            progress=STAGE_PROGRESS["failed"],
            error_message=f"Queue enqueue failed: {e}",
        )
        raise

    return job


def run_audit_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    user_id: str,
    doc_type: str,
    case_id: Optional[str] = None,
    file_url: Optional[str] = None,
    model_type: Optional[str] = None,
) -> None:
    try:
        t_start = time.perf_counter()
        selected_model = normalize_model_type(model_type)
        normalized_case_id = _normalize_case_id(case_id)
        with AUDIT_LOCK:
            existing_job = AUDIT_JOBS.get(job_id) or {}
            if not normalized_case_id:
                normalized_case_id = _normalize_case_id(existing_job.get("case_id"))
        if not normalized_case_id:
            normalized_case_id = str(uuid.uuid4())
        _ensure_case(normalized_case_id, user_id, doc_type)

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="cancelled")
            return
        update_job(
            job_id,
            status="running",
            progress=STAGE_PROGRESS["pending_docs"],
            stage="pending_docs",
            workflow_state="pending_docs",
            model_type=selected_model,
            case_id=normalized_case_id,
        )
        _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="running")

        update_job(job_id, progress=10, stage="ocr", workflow_state="extracting")

        raw_text, page_texts, ocr_confidence, extract_mode = _extract_text(file_bytes, filename)
        t_after_ocr = time.perf_counter()
        _update_case_document_entry(
            case_id=normalized_case_id,
            job_id=job_id,
            status="parsed",
            extract_mode=extract_mode,
            ocr_confidence=ocr_confidence,
            raw_text=raw_text,
        )
        _update_db("audit_docs", {
            "raw_text": raw_text,
            "page_texts": page_texts,
            "ocr_confidence": ocr_confidence,
        }, job_id, key="job_id")

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="cancelled")
            return

        effective_doc_type = doc_type
        if doc_type == "auto":
            llm_doc_type = _infer_doc_type_llm(raw_text, selected_model) if AUDIT_LLM_ENABLED else None
            effective_doc_type = llm_doc_type or _infer_doc_type(raw_text)
            update_job(job_id, doc_type=effective_doc_type)
            _update_db("audit_docs", {"doc_type": effective_doc_type}, job_id, key="job_id")
        _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, doc_type=effective_doc_type)

        update_job(job_id, progress=STAGE_PROGRESS["ocr"], stage="extract")

        extraction_text = _build_case_combined_text(normalized_case_id, job_id, raw_text)
        fields = _extract_fields(extraction_text, effective_doc_type, llm_backend=selected_model)
        fields = _validate_fields(fields)
        doc_subtype = _infer_doc_subtype(raw_text, effective_doc_type, fields, file_name=filename)
        if doc_subtype:
            fields["doc_subtype"] = doc_subtype
        t_after_extract = time.perf_counter()

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="cancelled")
            return

        history_records = _collect_history_records(user_id)
        feedback_ctx = _collect_review_feedback(user_id, effective_doc_type, history_records)
        erp_ctx = _fetch_erp_context(fields, user_id, effective_doc_type, history_records)

        update_job(job_id, progress=STAGE_PROGRESS["extract"], stage="rules", workflow_state="rule_checking")

        rule_findings = _run_rules(effective_doc_type, fields, extraction_text, erp_ctx)
        current_case_documents = _case_public_documents(normalized_case_id)
        cross_findings, erp_checks = _run_cross_document_checks(
            effective_doc_type,
            fields,
            erp_ctx,
            history_records,
            case_documents=current_case_documents,
        )
        anomaly_findings, anomaly_stats = _run_anomaly_detection(effective_doc_type, fields, history_records)
        deterministic_findings = list(rule_findings) + list(cross_findings) + list(anomaly_findings)
        t_after_rules = time.perf_counter()

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

        update_job(job_id, progress=STAGE_PROGRESS["rules"], stage="ai", workflow_state="ai_review")
        ai_assessment = _run_ai_review(
            effective_doc_type,
            fields,
            extraction_text,
            deterministic_findings,
            high_risk_gate,
            selected_model,
            erp_ctx,
            feedback_ctx,
            anomaly_stats,
        )
        t_after_ai = time.perf_counter()

        if _is_cancelled(job_id):
            update_job(job_id, status="cancelled", progress=100, stage="cancelled")
            _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="cancelled")
            return

        update_job(job_id, progress=STAGE_PROGRESS["ai"], stage="report", workflow_state="aggregating")

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
            if not _has_chinese_text(summary):
                summary = _build_summary(combined_findings)
        else:
            risk_level = _risk_level(deterministic_findings)
            is_pass = risk_level == "low"
            summary = _build_summary(deterministic_findings)

        recognized_doc_subtype = _safe_text(fields.get("doc_subtype")) or _infer_doc_subtype(
            raw_text,
            effective_doc_type,
            fields,
            file_name=filename,
        )
        if recognized_doc_subtype:
            fields["doc_subtype"] = recognized_doc_subtype

        summary = _append_doc_type_to_summary(summary, effective_doc_type, recognized_doc_subtype)
        recognized_doc_type = normalize_doc_type(effective_doc_type)
        recognized_doc_type_label = _doc_type_display_name(recognized_doc_type)
        recognized_doc_subtype_label = _doc_subtype_display_name(recognized_doc_subtype)

        case_documents = _case_public_documents(normalized_case_id)
        case_completeness = _evaluate_case_completeness(case_documents)
        if case_completeness.get("missing"):
            workflow_state = "pending_docs"
            next_action = "请补齐缺失单据后再完成终审。"
        elif risk_level == "high":
            workflow_state = "review_required"
            next_action = "建议转人工复核。"
        elif risk_level == "medium":
            workflow_state = "review_optional"
            next_action = "建议人工抽样复核。"
        else:
            workflow_state = "ready_for_erp"
            next_action = "可进入 ERP 回写队列。"

        update_job(job_id, stage="review", progress=STAGE_PROGRESS["review"], workflow_state=workflow_state)

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
            "recognized_doc_type": recognized_doc_type,
            "recognized_doc_type_label": recognized_doc_type_label,
            "recognized_doc_subtype": recognized_doc_subtype,
            "recognized_doc_subtype_label": recognized_doc_subtype_label,
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
            "model_type": selected_model,
            "text_extract_mode": extract_mode,
            "erp_action": None,
            "erp_trace_id": None,
            "workflow_state": workflow_state,
            "next_action": next_action,
            "upload_sequence": ["contract", "invoice", "packing_list", "bill_of_lading", "payment", "expense"],
            "upload_sequence_hint": "建议顺序：先合同，再贸易/履约单据，最后付款/报销单据。",
            "case_summary": {
                "case_id": normalized_case_id,
                "documents": case_documents,
                "completeness": case_completeness,
            },
        }

        _persist_audit_result(job_id, result)
        _update_case_document_entry(case_id=normalized_case_id, job_id=job_id, status="done", doc_type=effective_doc_type)

        update_job(
            job_id,
            status="done",
            progress=STAGE_PROGRESS["done"],
            stage="done",
            workflow_state=workflow_state,
            result=result,
        )
        t_done = time.perf_counter()
        print(
            "[Audit Perf] "
            f"job={job_id} "
            f"extract_mode={extract_mode} "
            f"ocr={t_after_ocr - t_start:.2f}s "
            f"extract={t_after_extract - t_after_ocr:.2f}s "
            f"rules={t_after_rules - t_after_extract:.2f}s "
            f"ai={t_after_ai - t_after_rules:.2f}s "
            f"report={t_done - t_after_ai:.2f}s "
            f"total={t_done - t_start:.2f}s"
        )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            progress=STAGE_PROGRESS["failed"],
            stage="failed",
            workflow_state="failed",
            error_message=str(e),
        )
        _update_case_document_entry(case_id=normalized_case_id if "normalized_case_id" in locals() else None, job_id=job_id, status="failed")
        raise



