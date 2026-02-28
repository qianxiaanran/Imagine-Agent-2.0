import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from supabase_client import require_supabase
except Exception:
    require_supabase = None

try:
    from deepseek_llm import ask_llm
except Exception:
    ask_llm = None

# ✅ [修复] 修正 LangChain 导入路径，优先使用 langchain_core
try:
    from deepseek_llm import get_llm_instance
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        try:
            from langchain.schema import HumanMessage, SystemMessage
        except ImportError:
            print("⚠️ [OCR Structured] 无法导入 HumanMessage/SystemMessage")
            HumanMessage = None
            SystemMessage = None
except Exception as e:
    print(f"⚠️ [OCR Structured] LangChain/DeepSeek 模块导入失败: {e}")
    get_llm_instance = None
    HumanMessage = None
    SystemMessage = None

OCR_LLM_ENABLED = os.getenv("OCR_LLM_ENABLED", "true").lower() != "false"
OCR_LLM_BACKEND = os.getenv("OCR_LLM_BACKEND", "local")
OCR_LLM_MAX_CHARS = int(os.getenv("OCR_LLM_MAX_CHARS", "6000"))


FIELD_DEFS: Dict[str, Dict[str, str]] = {
    "title": {"label": "文档标题", "type": "text", "placeholder": "如：采购合同/报关单"},
    "doc_no": {"label": "单据编号", "type": "text", "placeholder": "编号"},
    "doc_date": {"label": "单据日期", "type": "date", "placeholder": "YYYY-MM-DD"},
    "contract_no": {"label": "合同编号", "type": "text", "placeholder": "合同号"},
    "contract_date": {"label": "合同日期", "type": "date", "placeholder": "YYYY-MM-DD"},
    "invoice_no": {"label": "发票号", "type": "text", "placeholder": "发票号码"},
    "invoice_date": {"label": "开票日期", "type": "date", "placeholder": "YYYY-MM-DD"},
    "declaration_no": {"label": "报关单号", "type": "text", "placeholder": "报关单编号"},
    "customs_date": {"label": "申报日期", "type": "date", "placeholder": "YYYY-MM-DD"},
    "buyer": {"label": "采购方/买方", "type": "text", "placeholder": "公司名称"},
    "seller": {"label": "供应商/卖方", "type": "text", "placeholder": "公司名称"},
    "importer": {"label": "进口商/收货人", "type": "text", "placeholder": "公司名称"},
    "exporter": {"label": "出口商/发货人", "type": "text", "placeholder": "公司名称"},
    "vendor": {"label": "销售方/开票方", "type": "text", "placeholder": "公司名称"},
    "tax_no": {"label": "税号", "type": "text", "placeholder": "纳税人识别号"},
    "bank_account": {"label": "银行账号", "type": "text", "placeholder": "开户行/账号"},
    "goods_name": {"label": "商品名称", "type": "text", "placeholder": "货物/服务名称"},
    "hs_code": {"label": "HS 编码", "type": "text", "placeholder": "HS Code"},
    "subject": {"label": "标的/内容", "type": "textarea", "placeholder": "采购/销售内容摘要"},
    "total_amount": {"label": "金额", "type": "text", "placeholder": "金额"},
    "currency": {"label": "币种", "type": "text", "placeholder": "CNY / USD"},
    "remarks": {"label": "备注", "type": "textarea", "placeholder": "补充说明"},
}


DOC_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "purchase_contract": {
        "label": "采购合同",
        "sections": [
            {"title": "合同信息", "fields": ["contract_no", "contract_date", "total_amount", "currency"]},
            {"title": "交易双方", "fields": ["buyer", "seller"]},
            {"title": "采购内容", "fields": ["subject"]},
            {"title": "补充信息", "fields": ["remarks"]},
        ],
    },
    "sales_contract": {
        "label": "销售合同",
        "sections": [
            {"title": "合同信息", "fields": ["contract_no", "contract_date", "total_amount", "currency"]},
            {"title": "交易双方", "fields": ["buyer", "seller"]},
            {"title": "销售内容", "fields": ["subject"]},
            {"title": "补充信息", "fields": ["remarks"]},
        ],
    },
    "customs_declaration": {
        "label": "报关单",
        "sections": [
            {"title": "申报信息", "fields": ["declaration_no", "customs_date", "currency"]},
            {"title": "收发货人", "fields": ["importer", "exporter"]},
            {"title": "货物信息", "fields": ["goods_name", "hs_code", "total_amount"]},
            {"title": "补充信息", "fields": ["remarks"]},
        ],
    },
    "invoice": {
        "label": "发票",
        "sections": [
            {"title": "发票信息", "fields": ["invoice_no", "invoice_date", "total_amount", "currency"]},
            {"title": "销售方", "fields": ["vendor", "tax_no", "bank_account"]},
            {"title": "补充信息", "fields": ["remarks"]},
        ],
    },
    "contract": {
        "label": "合同",
        "sections": [
            {"title": "合同信息", "fields": ["contract_no", "contract_date", "total_amount", "currency"]},
            {"title": "合同双方", "fields": ["buyer", "seller"]},
            {"title": "合同内容", "fields": ["subject"]},
            {"title": "补充信息", "fields": ["remarks"]},
        ],
    },
    "generic": {
        "label": "通用文档",
        "sections": [
            {"title": "基础信息", "fields": ["title", "doc_no", "doc_date", "total_amount", "currency"]},
            {"title": "主体信息", "fields": ["buyer", "seller", "vendor"]},
            {"title": "内容摘要", "fields": ["subject", "remarks"]},
        ],
    },
}


def _strip_wrappers(value: str) -> str:
    cleaned = re.sub(r"^[\s:：\-\(\)\[\]（）【】]+", "", value)
    cleaned = re.sub(r"[\s:：\-\(\)\[\]（）【】]+$", "", cleaned)
    return cleaned


def _is_noise_value(value: Optional[str]) -> bool:
    if value is None:
        return True
    cleaned = str(value).strip()
    if not cleaned:
        return True
    if re.fullmatch(r"[\s:：\-\(\)\[\]（）【】]+", cleaned):
        return True
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", cleaned):
        return True
    return False


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = _strip_wrappers(str(value).strip())
    if _is_noise_value(cleaned):
        return None
    return cleaned or None


def _search_first(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return None


def _search_by_lines(text: str, keywords: List[str]) -> Optional[str]:
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        for kw in keywords:
            if kw not in line:
                continue
            for sep in (":", "："):
                if sep in line:
                    value = _clean(line.split(sep, 1)[1])
                    if value:
                        return value
            if line.endswith((":","：")) and idx + 1 < len(lines):
                value = _clean(lines[idx + 1])
                if value:
                    return value
    return None


def _search_by_keywords(text: str, keywords: List[str]) -> Optional[str]:
    line_hit = _search_by_lines(text, keywords)
    if line_hit:
        return line_hit
    patterns = [rf"{kw}\s*[:：]?\s*([^\n\r]+)" for kw in keywords]
    return _search_first(text, patterns)


def _normalize_date(value: str) -> Optional[str]:
    if not value:
        return None
    m = re.search(r"(\d{4})[年\./-](\d{1,2})[月\./-](\d{1,2})", value)
    if not m:
        return None
    year, month, day = m.groups()
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return None


def _find_date(text: str, keywords: Optional[List[str]] = None) -> Optional[str]:
    if keywords:
        candidate = _search_by_keywords(text, keywords)
        normalized = _normalize_date(candidate or "")
        if normalized:
            return normalized
    m = re.search(r"(\d{4})[年\./-](\d{1,2})[月\./-](\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _is_probable_year(value: str) -> bool:
    digits = value.replace(",", "").strip()
    if re.fullmatch(r"\d{4}", digits):
        year = int(digits)
        return 1900 <= year <= 2100
    return False


def _find_amount(text: str, keywords: Optional[List[str]] = None) -> Optional[str]:
    if keywords:
        pattern = rf"(?:{'|'.join(keywords)})\s*[:：]?\s*([0-9][0-9,\.]*)"
        match = re.search(pattern, text)
        if match:
            value = _clean(match.group(1))
            if value and not _is_probable_year(value):
                return value
    match = re.search(r"([0-9][0-9,\.]{2,})", text)
    if match:
        value = _clean(match.group(1))
        if value and not _is_probable_year(value):
            return value
    return None


def _find_currency(text: str) -> Optional[str]:
    if re.search(r"(人民币|CNY|RMB)", text, re.IGNORECASE):
        return "CNY"
    if re.search(r"(美元|USD|US\\$)", text, re.IGNORECASE):
        return "USD"
    if re.search(r"(欧元|EUR)", text, re.IGNORECASE):
        return "EUR"
    return None


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


def _merge_fields(base_fields: Dict[str, Optional[str]], llm_fields: Dict[str, Any]) -> Dict[str, Optional[str]]:
    merged = dict(base_fields)
    for key in merged.keys():
        value = llm_fields.get(key) if isinstance(llm_fields, dict) else None
        cleaned = _clean(value) if value is not None else None
        if cleaned:
            merged[key] = cleaned
    return merged


def _extract_with_llm(text: str, hint_type: Optional[str] = None, llm_backend: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not ask_llm or not OCR_LLM_ENABLED:
        return None
    trimmed = _truncate_text(text, OCR_LLM_MAX_CHARS)
    if not trimmed:
        return None
    backend = llm_backend or OCR_LLM_BACKEND
    doc_types_desc = "\n".join([f"- {key}: {value['label']}" for key, value in DOC_SCHEMAS.items()])
    field_desc = "\n".join([f"- {key}: {meta['label']}" for key, meta in FIELD_DEFS.items()])
    hint_note = f"提示：如果已给定类型，请优先使用类型 {hint_type}。" if hint_type else ""
    system_prompt = (
        "你是结构化抽取引擎，只输出严格 JSON。"
        "不要输出解释、不要输出 Markdown、不要包裹代码块。"
    )
    prompt = (
        "请从 OCR 文本中抽取结构化字段。\n"
        "文档类型候选列表:\n"
        f"{doc_types_desc}\n\n"
        "字段定义(通用 key -> 含义):\n"
        f"{field_desc}\n\n"
        "输出要求:\n"
        "1) 只输出 JSON，不要多余文字。\n"
        "2) JSON 结构为 {\"doc_type\":\"<type>\",\"fields\":{...}}。\n"
        "3) fields 仅包含候选字段 key，无法确定的值用空字符串。\n"
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
            response_obj = llm.invoke(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
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


def infer_doc_type(text: str, hint_type: Optional[str] = None) -> str:
    if hint_type and hint_type in DOC_SCHEMAS:
        return hint_type
    content = text or ""
    if "采购" in content and "合同" in content:
        return "purchase_contract"
    if "销售" in content and "合同" in content:
        return "sales_contract"
    if re.search(r"报关|海关|申报", content):
        return "customs_declaration"
    if re.search(r"采购合同|采购协议|采购订单", content):
        return "purchase_contract"
    if re.search(r"销售合同|销售协议|购销合同", content):
        return "sales_contract"
    if re.search(r"发票|增值税", content):
        return "invoice"
    if re.search(r"合同|协议|签署", content):
        return "contract"
    return "generic"


def _init_fields(doc_type: str) -> Dict[str, Optional[str]]:
    schema = DOC_SCHEMAS.get(doc_type, DOC_SCHEMAS["generic"])
    keys: List[str] = []
    for section in schema["sections"]:
        keys.extend(section["fields"])
    return {key: None for key in dict.fromkeys(keys)}


def extract_fields(text: str, doc_type: str) -> Dict[str, Optional[str]]:
    fields = _init_fields(doc_type)
    content = text or ""

    fields["currency"] = _find_currency(content)
    fields["total_amount"] = _find_amount(content, ["金额合计", "合同金额", "价税合计", "总金额", "合计", "总价"])
    fields["subject"] = _search_by_keywords(content, ["标的", "采购内容", "货物名称", "服务内容", "项目名称"])

    if doc_type in ("purchase_contract", "sales_contract", "contract"):
        fields["contract_no"] = _search_by_keywords(content, ["合同编号", "合同号", "合同编号/号", "协议编号"])
        fields["contract_date"] = _find_date(content, ["签订日期", "签署日期", "合同日期", "签约日期"])
        fields["buyer"] = _search_by_keywords(content, ["采购方", "买方", "甲方"])
        fields["seller"] = _search_by_keywords(content, ["供应商", "卖方", "乙方"])

    if doc_type == "purchase_contract":
        fields["buyer"] = fields["buyer"] or _search_by_keywords(content, ["采购方", "买方", "甲方"])
        fields["seller"] = fields["seller"] or _search_by_keywords(content, ["供应商", "卖方", "乙方"])

    if doc_type == "sales_contract":
        fields["buyer"] = fields["buyer"] or _search_by_keywords(content, ["买方", "甲方", "客户"])
        fields["seller"] = fields["seller"] or _search_by_keywords(content, ["卖方", "乙方", "销售方"])

    if doc_type == "customs_declaration":
        fields["declaration_no"] = _search_by_keywords(content, ["报关单号", "报关单编号", "海关编号"])
        fields["customs_date"] = _find_date(content, ["申报日期", "报关日期", "进口日期", "出口日期"])
        fields["importer"] = _search_by_keywords(content, ["进口商", "收货人", "收货单位"])
        fields["exporter"] = _search_by_keywords(content, ["出口商", "发货人", "发货单位"])
        fields["goods_name"] = _search_by_keywords(content, ["商品名称", "货物名称", "品名"])
        fields["hs_code"] = _search_by_keywords(content, ["HS编码", "商品编码", "税号"])

    if doc_type == "invoice":
        fields["invoice_no"] = _search_by_keywords(content, ["发票号码", "发票号", "票据号"])
        fields["invoice_date"] = _find_date(content, ["开票日期", "开票时间", "开票日"])
        fields["vendor"] = _search_by_keywords(content, ["销售方", "开票方", "销方"])
        fields["tax_no"] = _search_by_keywords(content, ["纳税人识别号", "税号"])
        fields["bank_account"] = _search_by_keywords(content, ["开户行", "账号", "开户银行"])

    if doc_type == "generic":
        fields["title"] = _search_by_keywords(content, ["标题", "文件名称", "文档标题"])
        fields["doc_no"] = _search_by_keywords(content, ["编号", "文号", "单据编号"])
        fields["doc_date"] = _find_date(content, ["日期", "制单日期", "开具日期"])
        fields["buyer"] = _search_by_keywords(content, ["买方", "甲方", "客户"])
        fields["seller"] = _search_by_keywords(content, ["卖方", "乙方", "供应商"])
        fields["vendor"] = _search_by_keywords(content, ["销售方", "开票方"])

    return fields


def build_schema(doc_type: str) -> Dict[str, Any]:
    schema = DOC_SCHEMAS.get(doc_type, DOC_SCHEMAS["generic"])
    field_meta = {
        key: FIELD_DEFS.get(key, {"label": key, "type": "text", "placeholder": ""})
        for section in schema["sections"]
        for key in section["fields"]
    }
    sections = []
    for section in schema["sections"]:
        sections.append({
            "title": section["title"],
            "fields": [
                {"key": key, **field_meta.get(key, {"label": key, "type": "text", "placeholder": ""})}
                for key in section["fields"]
            ],
        })
    return {
        "doc_type": doc_type,
        "label": schema["label"],
        "fields": field_meta,
        "sections": sections,
    }


def get_doc_type_options() -> List[Dict[str, str]]:
    return [{"value": key, "label": value["label"]} for key, value in DOC_SCHEMAS.items()]


def parse_ocr_content(
    content: str,
    hint_type: Optional[str] = None,
    llm_backend: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", content or "", flags=re.MULTILINE)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()

    llm_result = None
    if use_llm:
        llm_result = _extract_with_llm(cleaned, hint_type, llm_backend)

    effective_doc_type = None
    if hint_type and hint_type in DOC_SCHEMAS:
        effective_doc_type = hint_type
    elif llm_result and llm_result.get("doc_type") in DOC_SCHEMAS:
        effective_doc_type = llm_result.get("doc_type")
    else:
        effective_doc_type = infer_doc_type(cleaned, hint_type)

    fields = extract_fields(cleaned, effective_doc_type)
    if llm_result and isinstance(llm_result.get("fields"), dict):
        fields = _merge_fields(fields, llm_result.get("fields", {}))

    schema = build_schema(effective_doc_type)
    return {
        "doc_type": effective_doc_type,
        "doc_type_label": schema["label"],
        "fields": fields,
        "schema": schema,
        "doc_types": get_doc_type_options(),
    }


def save_ocr_record(
    doc_type: str,
    fields: Dict[str, Any],
    raw_text: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    if not require_supabase:
        return False, None, "Supabase unavailable"
    try:
        sb = require_supabase()
        now = datetime.utcnow().isoformat() + "Z"
        payload = {
            "doc_type": doc_type,
            "doc_type_label": DOC_SCHEMAS.get(doc_type, DOC_SCHEMAS["generic"])["label"],
            "fields": fields or {},
            "raw_text": raw_text or "",
            "user_id": user_id or "anonymous",
            "session_id": session_id,
            "title": title or DOC_SCHEMAS.get(doc_type, DOC_SCHEMAS["generic"])["label"],
            "created_at": now,
            "updated_at": now,
        }
        res = sb.table("ocr_records").insert(payload).execute()
        record_id = None
        if res.data and isinstance(res.data, list):
            record_id = res.data[0].get("id") if res.data[0] else None
        return True, record_id, None
    except Exception as e:
        return False, None, str(e)
