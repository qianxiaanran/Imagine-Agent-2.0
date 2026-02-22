from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import os
import hashlib
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# 🔧 配置区域：请在这里填入你的 API Key
# -----------------------------------------------------------------------------
# 1. Bing Web Search API (推荐，国内极稳): https://www.microsoft.com/en-us/bing/apis/bing-web-search-api
BING_SUBSCRIPTION_KEY = os.environ.get("BING_SEARCH_V7_KEY", "")

# 2. SerpAPI (备选): https://serpapi.com/
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "2000"))
RAG_MAX_ACTIVE_CONTEXT_CHARS = int(os.getenv("RAG_MAX_ACTIVE_CONTEXT_CHARS", "1200"))
RAG_MAX_CHUNK_CHARS = int(os.getenv("RAG_MAX_CHUNK_CHARS", "700"))
RAG_MAX_CHUNKS = int(os.getenv("RAG_MAX_CHUNKS", "6"))
RAG_MAX_KB_TEXT_CHARS = int(os.getenv("RAG_MAX_KB_TEXT_CHARS", "4200"))
FAST_CHAT_DIRECT = os.getenv("FAST_CHAT_DIRECT", "true").lower() != "false"
FAST_CHAT_HISTORY_LIMIT = int(os.getenv("FAST_CHAT_HISTORY_LIMIT", "4"))
PROMPT_LAYOUT_VERSION = "v1"
CONTEXT_EVENT_SCAN_LIMIT = int(os.getenv("CONTEXT_EVENT_SCAN_LIMIT", "30"))
CONTEXT_COMPACTION_SCAN_LIMIT = int(os.getenv("CONTEXT_COMPACTION_SCAN_LIMIT", "80"))
CONTEXT_COMPACTION_TRIGGER_CHARS = int(os.getenv("CONTEXT_COMPACTION_TRIGGER_CHARS", "8000"))
CONTEXT_COMPACTION_MIN_INTERVAL = int(os.getenv("CONTEXT_COMPACTION_MIN_INTERVAL", "8"))

# -----------------------------------------------------------------------------

from supabase_client import require_supabase
from history_manager import get_history, get_history_limited, get_user_sessions, delete_session, rename_session
from deepseek_llm import ask_llm_stream, ask_llm

# 引入我们新构建的模块（仅在 LangGraph 路径需要）
from context_hub import ContextHub

# ✅ 直接数据库查询：强制走 database_manager，不经过 langgraph
from database_manager import db_manager, DB_NAME as DEFAULT_DB_NAME

# ✅ 引入 Audit Service
try:
    from audit_service import run_audit_pipeline
except ImportError:
    print("⚠️ Audit Service not found, audit mode will fall back to general chat.")
    run_audit_pipeline = None

# 可选：文档检索（RAG 直连模式，不经过 langgraph）
search_user_documents = None
try:
    from documents_processing import search_user_documents  # type: ignore
except Exception as e:
    print(f"⚠️ [ChatRouter] documents_processing 未就绪，RAG 直连模式不可用: {e}")

# ✨ [修改] 增加安全导入，防止因为缺少 langgraph 导致整个后端无法启动
app_graph = None
memory_summary = None
try:
    from langgraph_agent import app_graph, _is_db_question_by_tables
    try:
        from langgraph_agent import memory_summary
    except Exception:
        memory_summary = None
except ImportError as e:
    _is_db_question_by_tables = None
    print(
        f"⚠️ [ChatRouter] 警告: 无法导入 langgraph_agent ({e})。请确保安装了 langgraph: `pip install langgraph langchain-core`")
except Exception as e:
    _is_db_question_by_tables = None
    print(f"⚠️ [ChatRouter] langgraph_agent 加载失败: {e}")

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    user_id: Optional[str] = None
    session_id: Optional[str] = None

    # ✅ 前端会传：mode / modelId
    mode: Optional[str] = Field(default="general", description="对话模式：general / database / rag / search / audit ...")
    modelId: Optional[str] = Field(default=None, description="前端选择的模型ID（字符串）")

    # ✨ [新增] 模型后端选择
    model_backend: Optional[str] = Field(default="local", description="backend: local (Qwen) / cloud (DeepSeek)")

    # 上下文内容（OCR/会议/订单文本）
    context_content: Optional[str] = None
    # 显式文件列表 (预留)
    files: List[str] = []
    personalization: Dict[str, Any] = Field(default_factory=dict)


class RenameRequest(BaseModel):
    title: str


# ------------------------------------------------------------
# 辅助函数：构建历史消息对象
# ------------------------------------------------------------
def _sanitize_history_content(text: str) -> str:
    """清洗历史内容，避免把调试/工具日志混入上下文导致模型跑偏。"""
    if text is None:
        return ""
    s = str(text)

    # 移除一些可能出现在文本里的特殊标记
    s = s.replace("<|im_start|>", "").replace("<|im_end|>", "")
    # 移除前端/中间层注入的 meta 行
    s = re.sub(r'^\s*Assistant:\s*\{.*?\}\s*$', '', s, flags=re.MULTILINE)
    # 移除 Explainable AI/工具思考日志
    s = re.sub(r'^\s*>\s*🧠.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*🧠.*$', '', s, flags=re.MULTILINE)

    # ✨ [新增] 移除 搜索过程 日志 (防止下次对话时 LLM 看到这些临时状态)
    s = re.sub(r'^\s*>\s*🔍.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*📄.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*🤔.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*⚠️.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*☁️.*$', '', s, flags=re.MULTILINE)  # 天气
    s = re.sub(r'^\s*>\s*📈.*$', '', s, flags=re.MULTILINE)  # 股票
    s = re.sub(r'^\s*>\s*🔄.*$', '', s, flags=re.MULTILINE)  # 重试

    # 移除 ReAct 过程日志
    s = re.sub(r'^\s*ReAct\s*(思考|行动|观察).*$', '', s, flags=re.MULTILINE)
    # 移除各种调试图标日志行
    s = re.sub(r'^\s*[🔍🗄️📅🚦⚙️📢].*$', '', s, flags=re.MULTILINE)
    # 多余空行收敛
    s = re.sub(r'\n{3,}', '\n\n', s)

    return s.strip()


def _looks_like_meeting_minutes(text: str) -> bool:
    if not text:
        return False
    s = str(text)
    markers = [
        "会议主题",
        "关键决策",
        "行动项",
        "风险与待确认事项",
        "会议纪要",
    ]
    hit_count = sum(1 for marker in markers if marker in s)
    return hit_count >= 2


def _truncate_context(text: Optional[str], max_len: int = MAX_CONTEXT_CHARS) -> str:
    if not text:
        return ""
    s = str(text)
    if len(s) <= max_len:
        return s
    return s[:max_len]


_ALLOWED_STYLE_TONES = {"default", "concise", "warm", "direct"}
_ALLOWED_TRAIT_LEVELS = {"default", "low", "medium", "high"}
_ALLOWED_REPLY_LANGUAGES = {"zh-CN", "en-US"}


def _safe_pref_text(value: Any, max_len: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_len]


def _normalize_personalization(raw: Optional[Dict[str, Any]]) -> Dict[str, str]:
    data = raw or {}
    style_tone = str(data.get("styleTone") or "default")
    trait_warm = str(data.get("traitWarm") or "default")
    trait_enthusiasm = str(data.get("traitEnthusiasm") or "default")
    trait_titles = str(data.get("traitTitles") or "default")
    trait_emoji = str(data.get("traitEmoji") or "default")
    reply_language = str(data.get("replyLanguage") or "zh-CN")

    if style_tone not in _ALLOWED_STYLE_TONES:
        style_tone = "default"
    if trait_warm not in _ALLOWED_TRAIT_LEVELS:
        trait_warm = "default"
    if trait_enthusiasm not in _ALLOWED_TRAIT_LEVELS:
        trait_enthusiasm = "default"
    if trait_titles not in _ALLOWED_TRAIT_LEVELS:
        trait_titles = "default"
    if trait_emoji not in _ALLOWED_TRAIT_LEVELS:
        trait_emoji = "default"
    if reply_language not in _ALLOWED_REPLY_LANGUAGES:
        reply_language = "zh-CN"

    return {
        "styleTone": style_tone,
        "traitWarm": trait_warm,
        "traitEnthusiasm": trait_enthusiasm,
        "traitTitles": trait_titles,
        "traitEmoji": trait_emoji,
        "replyLanguage": reply_language,
        "aboutNickname": _safe_pref_text(data.get("aboutNickname"), max_len=80),
        "customInstruction": _safe_pref_text(data.get("customInstruction"), max_len=600),
    }


def _build_personalization_system_prompt(preferences: Dict[str, str]) -> Optional[str]:
    if not preferences:
        return None

    lines: List[str] = []

    reply_language = preferences.get("replyLanguage", "zh-CN")
    if reply_language == "en-US":
        lines.append("Default reply language: English. Switch language only when user explicitly asks.")

    style_tone = preferences.get("styleTone", "default")
    if style_tone == "concise":
        lines.append("Keep responses concise, practical, and execution-focused.")
    elif style_tone == "warm":
        lines.append("Use a warm and supportive tone while staying clear and actionable.")
    elif style_tone == "direct":
        lines.append("State conclusions directly, then give key reasons and concrete steps.")

    trait_warm = preferences.get("traitWarm", "default")
    if trait_warm == "low":
        lines.append("Use neutral tone; avoid overly emotional wording.")
    elif trait_warm == "medium":
        lines.append("Use moderate empathy in wording.")
    elif trait_warm == "high":
        lines.append("Use clearly warm and considerate wording where natural.")

    trait_enthusiasm = preferences.get("traitEnthusiasm", "default")
    if trait_enthusiasm == "low":
        lines.append("Keep emotional intensity low and steady.")
    elif trait_enthusiasm == "medium":
        lines.append("Use moderate enthusiasm in expression.")
    elif trait_enthusiasm == "high":
        lines.append("Use energetic and proactive language.")

    trait_titles = preferences.get("traitTitles", "default")
    if trait_titles == "low":
        lines.append("Prefer short paragraphs; use headings/lists only when necessary.")
    elif trait_titles == "medium":
        lines.append("Use headings/lists in a balanced way for readability.")
    elif trait_titles == "high":
        lines.append("Proactively use clear headings and bullet points.")

    trait_emoji = preferences.get("traitEmoji", "default")
    if trait_emoji == "low":
        lines.append("Do not use emoji.")
    elif trait_emoji == "medium":
        lines.append("Use emoji sparingly, only when helpful.")
    elif trait_emoji == "high":
        lines.append("You may use a few suitable emoji, but keep business readability.")

    nickname = preferences.get("aboutNickname", "")
    if nickname:
        lines.append(f"When appropriate, address the user as: {nickname}")

    custom_instruction = preferences.get("customInstruction", "")
    if custom_instruction:
        lines.append(f"Custom user instruction: {custom_instruction}")

    if not lines:
        return None

    return (
        "Follow these user preferences for response style only. "
        "Do not alter factuality, safety, or policy boundaries.\n- "
        + "\n- ".join(lines)
    )


def _merge_system_prompt(base_prompt: Optional[str], preference_prompt: Optional[str]) -> Optional[str]:
    if base_prompt and preference_prompt:
        return f"{base_prompt}\n\n{preference_prompt}"
    return base_prompt or preference_prompt


def _stable_json_dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_json_loads(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    code_match = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if code_match:
        text = code_match.group(1).strip()
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_text_list(value: Any, max_items: int = 8, max_len: int = 160) -> List[str]:
    items: List[str] = []
    if isinstance(value, list):
        for it in value:
            if not isinstance(it, str):
                continue
            s = " ".join(it.strip().split())
            if not s:
                continue
            s = s[:max_len]
            if s not in items:
                items.append(s)
            if len(items) >= max_items:
                break
    return items


def _normalize_compaction_payload(
        payload: Dict[str, Any],
        source_chars: int,
        source_messages: int,
) -> Dict[str, Any]:
    summary = _safe_pref_text(payload.get("summary"), max_len=1200)
    if not summary:
        summary = _safe_pref_text(payload.get("abstract"), max_len=1200)
    normalized = {
        "v": 1,
        "summary": summary,
        "facts": _normalize_text_list(payload.get("facts"), max_items=10, max_len=180),
        "preferences": _normalize_text_list(payload.get("preferences"), max_items=8, max_len=140),
        "constraints": _normalize_text_list(payload.get("constraints"), max_items=8, max_len=180),
        "open_items": _normalize_text_list(payload.get("open_items"), max_items=8, max_len=180),
        "source_chars": int(max(0, source_chars)),
        "source_messages": int(max(0, source_messages)),
        "layout_version": PROMPT_LAYOUT_VERSION,
    }
    return normalized


def _build_compaction_context_block(payload: Optional[Dict[str, Any]]) -> str:
    data = payload or {}
    if not isinstance(data, dict):
        return ""
    summary = _safe_pref_text(data.get("summary"), max_len=1200)
    facts = _normalize_text_list(data.get("facts"), max_items=10, max_len=180)
    preferences = _normalize_text_list(data.get("preferences"), max_items=8, max_len=140)
    constraints = _normalize_text_list(data.get("constraints"), max_items=8, max_len=180)
    open_items = _normalize_text_list(data.get("open_items"), max_items=8, max_len=180)
    if not any([summary, facts, preferences, constraints, open_items]):
        return ""

    sections: List[str] = []
    if summary:
        sections.append("Summary:\n" + summary)
    if facts:
        sections.append("Facts:\n- " + "\n- ".join(facts))
    if preferences:
        sections.append("Preferences:\n- " + "\n- ".join(preferences))
    if constraints:
        sections.append("Constraints:\n- " + "\n- ".join(constraints))
    if open_items:
        sections.append("OpenItems:\n- " + "\n- ".join(open_items))
    return "\n\n".join(sections)


def _build_cache_friendly_prompt(
        user_message: str,
        session_state: str = "",
        summary_context: str = "",
        recent_history: str = "",
) -> str:
    def section(name: str, content: str, allow_empty: bool = False) -> str:
        body = (content or "").strip()
        if not body and not allow_empty:
            body = "(empty)"
        return f"[{name}]\n{body}"

    blocks = [
        section("PromptLayout", f"version={PROMPT_LAYOUT_VERSION}"),
        section("SessionState", session_state),
        section("SummaryContext", summary_context),
        section("RecentHistory", recent_history),
        section("User", user_message),
        section("Assistant", "", allow_empty=True),
    ]
    return "\n\n".join(blocks)


def _read_recent_history_records(user_id: str, session_id: str, limit: int) -> List[Dict[str, Any]]:
    if user_id == "anonymous":
        return []
    try:
        return get_history_limited(user_id, session_id, limit=limit) or []
    except Exception:
        return []


def _append_meta_history_event(user_id: str, session_id: str, func_type: str, payload: Dict[str, Any]):
    if user_id == "anonymous":
        return
    try:
        sb = require_supabase()
        sb.table("history").insert({
            "user_id": user_id,
            "session_id": session_id,
            "role": "meta",
            "content": _stable_json_dumps(payload),
            "func_type": func_type,
        }).execute()
    except Exception as e:
        print(f"⚠️ Context event save failed ({func_type}): {e}")


def _latest_meta_event(records: List[Dict[str, Any]], func_type: str) -> Optional[Dict[str, Any]]:
    target = (func_type or "").strip().lower()
    for r in reversed(records):
        if (r.get("role") or "").strip().lower() != "meta":
            continue
        if ((r.get("func_type") or "").strip().lower()) != target:
            continue
        data = _safe_json_loads(r.get("content"))
        if data:
            return data
    return None


def _build_context_event_payload(
        mode: str,
        model_id: str,
        model_backend: str,
        context_content: str,
        personalization: Dict[str, str],
) -> Dict[str, Any]:
    base = {
        "v": 1,
        "mode": mode or "general",
        "model_id": model_id or "",
        "model_backend": model_backend or "local",
        "has_context": bool((context_content or "").strip()),
        "context_chars": len(context_content or ""),
        "reply_language": personalization.get("replyLanguage", "zh-CN"),
        "style_tone": personalization.get("styleTone", "default"),
    }
    payload = dict(base)
    payload["sig"] = hashlib.sha1(_stable_json_dumps(base).encode("utf-8")).hexdigest()
    payload["layout_version"] = PROMPT_LAYOUT_VERSION
    return payload


def _maybe_append_context_event(
        user_id: str,
        session_id: str,
        mode: str,
        model_id: str,
        model_backend: str,
        context_content: str,
        personalization: Dict[str, str],
):
    if user_id == "anonymous":
        return
    records = _read_recent_history_records(user_id, session_id, limit=CONTEXT_EVENT_SCAN_LIMIT)
    latest = _latest_meta_event(records, "context_event")
    payload = _build_context_event_payload(
        mode=mode,
        model_id=model_id,
        model_backend=model_backend,
        context_content=context_content,
        personalization=personalization,
    )
    if latest and latest.get("sig") == payload.get("sig"):
        return
    _append_meta_history_event(user_id, session_id, "context_event", payload)


def _collect_compaction_source_lines(records: List[Dict[str, Any]], mode: Optional[str]) -> List[str]:
    lines: List[str] = []
    current_mode = (mode or "").strip().lower()
    for r in records:
        role = (r.get("role") or "").strip().lower()
        if role == "meta":
            continue
        func_type = (r.get("func_type") or "").strip().lower()
        if current_mode != "meeting" and func_type == "meeting":
            continue
        content = _sanitize_history_content(r.get("content"))
        if not content:
            continue
        if current_mode != "meeting" and role == "assistant" and _looks_like_meeting_minutes(content):
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
        elif role == "context":
            lines.append(f"Context: {content}")
    return lines


def _messages_since_last_compaction(records: List[Dict[str, Any]]) -> int:
    count = 0
    for r in reversed(records):
        role = (r.get("role") or "").strip().lower()
        func_type = (r.get("func_type") or "").strip().lower()
        if role == "meta" and func_type == "context_compaction":
            break
        if role in {"user", "assistant", "context"}:
            count += 1
    return count


def _maybe_compact_context(
        user_id: str,
        session_id: str,
        mode: Optional[str],
        model_backend: str,
) -> Optional[Dict[str, Any]]:
    if user_id == "anonymous":
        return None

    records = _read_recent_history_records(user_id, session_id, limit=CONTEXT_COMPACTION_SCAN_LIMIT)
    if not records:
        return None

    latest_payload = _latest_meta_event(records, "context_compaction")
    source_lines = _collect_compaction_source_lines(records, mode=mode)
    if not source_lines:
        return latest_payload

    source_text = "\n".join(source_lines).strip()
    source_chars = len(source_text)
    if source_chars < CONTEXT_COMPACTION_TRIGGER_CHARS:
        return latest_payload

    since_last = _messages_since_last_compaction(records)
    if latest_payload and since_last < CONTEXT_COMPACTION_MIN_INTERVAL:
        return latest_payload

    compact_prompt = (
        "You are a context compactor for an enterprise assistant.\n"
        "Summarize the dialogue into stable, reusable state as strict JSON.\n"
        "Required JSON keys: summary, facts, preferences, constraints, open_items.\n"
        "- Keep facts verifiable and concise.\n"
        "- Keep user preferences and hard constraints explicit.\n"
        "- Do not include tool logs, status lines, or transient debug text.\n"
        "- Use Chinese output in JSON values.\n\n"
        f"Conversation:\n{source_text[:12000]}\n\n"
        "Return JSON only."
    )

    try:
        raw = ask_llm(compact_prompt, model_type=model_backend)
        parsed = _safe_json_loads(raw)
        normalized = _normalize_compaction_payload(
            parsed,
            source_chars=source_chars,
            source_messages=len(source_lines),
        )
        has_content = bool(
            normalized.get("summary")
            or normalized.get("facts")
            or normalized.get("preferences")
            or normalized.get("constraints")
            or normalized.get("open_items")
        )
        if not has_content:
            return latest_payload
        _append_meta_history_event(user_id, session_id, "context_compaction", normalized)
        return normalized
    except Exception as e:
        print(f"⚠️ Context compaction failed: {e}")
        return latest_payload


def _get_plain_history(user_id: str, session_id: str, limit: int = 4, mode: Optional[str] = None) -> str:
    """获取纯文本历史，用于 LLM 生成搜索词"""
    if user_id == "anonymous":
        return ""
    try:
        records = get_history_limited(user_id, session_id, limit=limit)
        # 取最近几条
        recent = records[-limit:]
        history_str = ""
        current_mode = (mode or "").strip().lower()
        for r in recent:
            raw_role = r.get('role')
            if raw_role == 'meta':
                continue
            raw_func_type = (r.get("func_type") or "").strip().lower()
            if current_mode != "meeting" and raw_func_type == "meeting":
                continue
            if raw_role == 'user':
                role = "User"
            elif raw_role == 'assistant':
                role = "Assistant"
            elif raw_role == 'context':
                role = "Context"
            else:
                role = "Assistant"

            content = _sanitize_history_content(r.get('content'))
            if current_mode != "meeting" and role == "Assistant" and _looks_like_meeting_minutes(content):
                continue
            if content:
                history_str += f"{role}: {content}\n"
        return history_str
    except Exception:
        return ""


def _get_langchain_history(user_id: str, session_id: str, limit: int = 6, mode: Optional[str] = None):
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    if user_id == "anonymous":
        return []
    try:
        records = get_history_limited(user_id, session_id, limit=limit)
        messages = []
        current_mode = (mode or "").strip().lower()
        for r in records[-limit:]:
            role = r.get('role')
            content = _sanitize_history_content(r.get('content'))
            raw_func_type = (r.get("func_type") or "").strip().lower()
            if current_mode != "meeting" and raw_func_type == "meeting":
                continue
            if current_mode != "meeting" and role == 'assistant' and _looks_like_meeting_minutes(content):
                continue
            if not content:
                continue
            if role == 'user':
                messages.append(HumanMessage(content=content))
            elif role == 'assistant':
                messages.append(AIMessage(content=content))
            elif role == 'context':
                messages.append(SystemMessage(content=f"Context: {content}"))
            else:
                messages.append(AIMessage(content=content))
        return messages
    except Exception:
        return []


def _normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "general").strip().lower()
    if m in {"db", "database", "sql"}:
        return "database"
    if m in {"rag", "doc", "docs", "document", "documents", "kb"}:
        return "rag"
    if m in {"web", "search", "internet"}:
        return "search"
    if m in {"audit", "review", "risk"}:
        return "audit"
    if m in {"general", "chat", "default"}:
        return "general"
    return m


def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _make_snippet(text: Optional[str], limit: int = 90) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def _build_doc_source(metadata: Dict[str, Any], content: Optional[str]) -> Dict[str, Any]:
    file_name = (
        metadata.get("file_name")
        or metadata.get("source")
        or metadata.get("filename")
        or metadata.get("title")
        or "文档"
    )
    src_type = metadata.get("type")
    page_display = None
    if src_type != "ocr":
        file_lower = str(file_name).lower()
        is_pdf = file_lower.endswith(".pdf")
        page_index = metadata.get("page_index")
        if page_index is not None:
            page_num = _safe_int(page_index)
            if page_num is not None:
                page_display = page_num + 1
        else:
            raw_page = metadata.get("page") if "page" in metadata else metadata.get("page_number")
            page_num = _safe_int(raw_page)
            if page_num is not None:
                if is_pdf and page_num >= 0:
                    page_display = page_num + 1
                else:
                    page_display = page_num if page_num > 0 else 1

    title = file_name
    if page_display:
        title = f"{file_name} · 第{page_display}页"

    snippet = metadata.get("snippet") or _make_snippet(content)
    source = {
        "title": title,
        "file_name": file_name,
        "page": page_display,
        "snippet": snippet,
    }
    if metadata.get("source"):
        source["source"] = metadata.get("source")
    if src_type:
        source["type"] = src_type
    return source


def _to_text_and_sources(items) -> tuple[list[str], list[Dict[str, Any]]]:
    """把 search_user_documents 的返回值（可能是 Document 对象或字符串）统一成文本列表 + 来源列表。"""
    texts: list[str] = []
    srcs: list[Dict[str, Any]] = []
    if not items:
        return texts, srcs

    for it in items:
        if it is None:
            continue
        # 直接字符串
        if isinstance(it, str):
            t = it.strip()
            if t:
                texts.append(t)
            continue

        # LangChain Document
        page_content = getattr(it, "page_content", None)
        metadata = getattr(it, "metadata", None)

        if isinstance(page_content, str) and page_content.strip():
            texts.append(page_content.strip())

        # 组装来源（尽量友好，不抛异常）
        if isinstance(metadata, dict):
            src = _build_doc_source(metadata, page_content if isinstance(page_content, str) else None)
            src_key = f"{src.get('file_name')}|{src.get('page')}|{src.get('snippet')}"
            existing_keys = {
                f"{s.get('file_name')}|{s.get('page')}|{s.get('snippet')}"
                for s in srcs
            }
            if src_key and src_key not in existing_keys:
                srcs.append(src)

    return texts, srcs


# ------------------------------------------------------------
# 🛠️ 搜索结果打分与优化模块 (新增)
# ------------------------------------------------------------
HIGH_VALUE_DOMAINS = [
    ".gov", ".edu", ".org",  # 政府、教育、非盈利
    "github.com", "stackoverflow.com", "huggingface.co", "arxiv.org",  # 技术社区
    "wikipedia.org", "baike.baidu.com",  # 百科
    "docs.python.org", "pytorch.org", "tensorflow.org",  # 官方文档
    "apple.com", "microsoft.com", "google.com", "aws.amazon.com",  # 科技巨头官网
    "caixin.com", "xinhuanet.com", "people.com.cn"  # 权威媒体
]

LOW_VALUE_DOMAINS = [
    "zhidao.baidu.com", "wenku.baidu.com",  # 很多时候需要付费或质量参差不齐
    "csdn.net",  # 广告多，重复内容多 (视情况调整权重)
    "bilibili.com"  # 视频站对文本问答贡献通常较小，除非是专栏
]


def _calculate_result_score(result: dict, query_keywords: List[str]) -> float:
    """计算单个搜索结果的相关性分数"""
    score = 0.0
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    link = result.get("link", "").lower()

    # 1. 关键词匹配 (简单加权)
    for kw in query_keywords:
        kw = kw.lower()
        if kw in title:
            score += 3.0  # 标题包含关键词权重高
        if kw in snippet:
            score += 1.0  # 摘要包含关键词

    # 2. 域名权威性加权
    domain_boost = False
    for domain in HIGH_VALUE_DOMAINS:
        if domain in link:
            score += 5.0  # 官方/权威域名大幅加分
            domain_boost = True
            break

    # 3. 低质域名降权
    if not domain_boost:
        for domain in LOW_VALUE_DOMAINS:
            if domain in link:
                score -= 2.0

    # 4. 惩罚过短的摘要
    if len(snippet) < 20:
        score -= 5.0

    return score


def _rank_search_results(results: List[dict], query: str, min_score: float = 3.0) -> List[dict]:
    """对搜索结果进行打分、排序和过滤"""
    if not results:
        return []

    # 简单分词 (按空格分，如果是中文其实最好用结巴，这里为了轻量化用简单逻辑)
    # 对于中文，简单的把 query 作为整体或者按空格切分
    keywords = [k for k in query.split() if len(k) > 1]
    if not keywords:
        keywords = [query]

    scored_results = []
    for r in results:
        score = _calculate_result_score(r, keywords)
        # 将分数附加到对象中方便调试，但不返回给前端
        r["_score"] = score
        if score >= min_score:
            scored_results.append(r)

    # 按分数降序排列
    scored_results.sort(key=lambda x: x["_score"], reverse=True)

    return scored_results


# ------------------------------------------------------------
# 🛠️ 工具函数：结构化数据 API (天气 / 股票)
# ------------------------------------------------------------
def tool_get_weather(city_name: str) -> List[dict]:
    """获取天气信息 (使用 wttr.in, 中国大陆可用)"""
    import requests
    results = []
    print(f"☁️ [Weather Tool] Getting weather for: {city_name}")
    try:
        # format=3: 简单的一行天气 (e.g., "Beijing: ☀️ +25°C")
        # lang=zh-cn: 中文
        url = f"https://wttr.in/{urllib.parse.quote(city_name)}?format=3&lang=zh-cn"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            weather_str = resp.text.strip()
            results.append({
                "title": f"{city_name} 实时天气",
                "link": f"https://wttr.in/{urllib.parse.quote(city_name)}",
                "snippet": f"当前天气状况: {weather_str}"
            })
    except Exception as e:
        print(f"⚠️ [Weather Tool] Failed: {e}")
    return results


def tool_get_stock(query: str) -> List[dict]:
    """获取股票信息 (使用新浪财经接口, 中国大陆极速)"""
    import requests
    results = []
    print(f"📈 [Stock Tool] Analyzing query: {query}")
    try:
        # 1. 简单的正则匹配股票代码 (支持 sh/sz/hk/us)
        # 如果用户输入 "贵州茅台股价"，这里需要先有一个 Search 步骤去换取代码，
        # 为了简化，我们先尝试直接搜索，如果用户输入代码则精确匹配。
        # 这里做一个简化策略：如果包含中文，先去 suggest 接口拿代码

        stock_code = ""
        market = ""

        # Match stock code (e.g. sh600519 / sz000001 / 600519 / AAPL)
        code_match = re.search(r"\b(?:sh|sz|hk|us)?\d{5,6}\b", query.lower())
        ticker_match = re.search(r"\b[A-Z]{2,6}\b", query)
        if code_match:
            code = code_match.group(0)
            if code.startswith(("sh", "sz", "hk", "us")):
                stock_code = code
            else:
                stock_code = f"sh{code}" if code.startswith("6") else f"sz{code}"
        elif ticker_match and len(query) <= 10:
            stock_code = ticker_match.group(0).lower()

        # 使用新浪 Suggest 接口获取代码
        suggest_url = f"https://suggest3.sinajs.cn/suggest/type=&key={urllib.parse.quote(query)}&name=suggestdata_{int(uuid4().int % 10000)}"
        # headers = {"Referer": "https://finance.sina.com.cn/"} # 这里的 Referer 不是必须的，但加上更好
        resp = requests.get(suggest_url, timeout=5)

        if resp.status_code == 200:
            # 格式: var suggestdata_xxx="贵州茅台,11,600519,sh600519,..."
            match = re.search(r'="(.*?)"', resp.text)
            if match and len(match.group(1)) > 5:
                # 取第一个结果
                data = match.group(1).split(',')
                # data[3] 通常是带市场前缀的代码 (e.g. sh600519)
                stock_code = data[3]
                stock_name = data[0]

        if stock_code:
            # 2. 获取实时行情
            hq_url = f"http://hq.sinajs.cn/list={stock_code}"
            headers = {"Referer": "https://finance.sina.com.cn/"}
            hq_resp = requests.get(hq_url, headers=headers, timeout=5)
            # 格式: var hq_str_sh600519="贵州茅台,1788.00,..."
            if hq_resp.status_code == 200:
                content = hq_resp.text
                val_match = re.search(r'="(.*?)"', content)
                if val_match:
                    vals = val_match.group(1).split(',')
                    if len(vals) > 30:  # A股格式
                        open_p, prev_close, price, high, low = vals[1], vals[2], vals[3], vals[4], vals[5]
                        date, time = vals[30], vals[31]
                        change = float(price) - float(prev_close)
                        percent = (change / float(prev_close)) * 100

                        results.append({
                            "title": f"{stock_name} ({stock_code}) 实时行情",
                            "link": f"https://finance.sina.com.cn/realstock/company/{stock_code}/nc.shtml",
                            "snippet": f"当前价格: ¥{price}\n涨跌幅: {percent:.2f}%\n涨跌额: {change:.2f}\n今开: {open_p} | 最高: {high} | 最低: {low}\n时间: {date} {time}"
                        })
                    elif len(vals) > 5:  # 美股/港股格式略有不同，做简单容错
                        price = vals[1] if len(vals) > 1 else "N/A"
                        results.append({
                            "title": f"{stock_name} ({stock_code}) 实时行情",
                            "link": f"https://finance.sina.com.cn",
                            "snippet": f"当前价格: {price} (详细数据请点击链接)"
                        })

    except Exception as e:
        print(f"⚠️ [Stock Tool] Failed: {e}")

    return results


# ------------------------------------------------------------
# 🛠️ 核心搜索工具：官方 API + 爬虫兜底
# ------------------------------------------------------------
def perform_web_search(query: str, max_results: int = 8) -> List[dict]:
    """
    智能搜索路由：
    1. 意图识别 -> 天气/股票结构化 API
    2. Bing API (如有 Key)
    3. SerpAPI (如有 Key)
    4. 爬虫兜底 (Bing CN / Sogou)
    """
    results = []

    # --- 1. 意图识别 (简单的关键词匹配) ---
    q_lower = query.lower()
    if "天气" in q_lower or "weather" in q_lower or "气温" in q_lower:
        # 提取地名简单的做法：交给 tool 处理，tool 会把整个 query 传给 wttr.in，它很聪明
        # 这里简单清洗一下 query，比如 "北京天气" -> "北京"
        city = query.replace("天气", "").replace("气温", "").replace("weather", "").strip()
        if not city: city = "Shanghai"  # 默认

        weather_res = tool_get_weather(city)
        if weather_res:
            return weather_res  # 如果命中结构化数据，直接返回，不再搜索网页

    if any(k in q_lower for k in ["股价", "股票", "行情", "stock", "price"]):
        stock_res = tool_get_stock(query)
        if stock_res:
            return stock_res

    # --- 2. 官方 API 搜索 ---

    # [Option A] Bing Web Search API
    if BING_SUBSCRIPTION_KEY:
        print(f"🔍 [Search] Using Official Bing API for: {query}")
        try:
            import requests
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": BING_SUBSCRIPTION_KEY}
            params = {"q": query, "count": max_results, "mkt": "zh-CN"}

            resp = requests.get(endpoint, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                web_pages = data.get("webPages", {}).get("value", [])
                for page in web_pages:
                    results.append({
                        "title": page.get("name"),
                        "link": page.get("url"),
                        "snippet": page.get("snippet", "")
                    })
                return results  # 成功则直接返回
            else:
                print(f"⚠️ [Bing API] Error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"⚠️ [Bing API] Exception: {e}")

    # [Option B] SerpAPI
    elif SERPAPI_API_KEY:
        print(f"🔍 [Search] Using SerpAPI (Bing Engine) for: {query}")
        try:
            import requests
            # 优先使用 Bing 引擎，因为国内内容更全
            params = {
                "engine": "bing",
                "q": query,
                "api_key": SERPAPI_API_KEY,
                "cc": "CN"  # Country Code
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                organic = data.get("organic_results", [])
                for res in organic[:max_results]:
                    results.append({
                        "title": res.get("title"),
                        "link": res.get("link"),
                        "snippet": res.get("snippet", "")
                    })
                return results
        except Exception as e:
            print(f"⚠️ [SerpAPI] Exception: {e}")

    # --- 3. 爬虫兜底 (Fallback) ---
    print(f"🔍 [Search] Fallback to Web Scraping (Bing/Sogou)...")
    return _perform_web_search_scraping(query, max_results)


def _perform_web_search_scraping(query: str, max_results: int) -> List[dict]:
    """(私有函数) 之前的爬虫实现，作为兜底方案"""
    results = []
    import requests
    from bs4 import BeautifulSoup

    # ------------------ 引擎 1: Bing CN ------------------
    try:
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://cn.bing.com/",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            list_items = soup.select('#b_results > li')
            for item in list_items:
                if len(results) >= max_results: break
                if "b_ad" in item.get("class", []): continue
                title_tag = item.select_one('h2 > a')
                if not title_tag: continue
                title = title_tag.get_text(strip=True)
                link = title_tag.get('href')
                if not link or link.startswith('/'): continue
                snippet = ""
                for selector in ['.b_caption p', '.b_snippet', '.caption', '.b_algoSlug']:
                    s_tag = item.select_one(selector)
                    if s_tag:
                        snippet = s_tag.get_text(strip=True)
                        break
                if not snippet: snippet = item.get_text(strip=True)[:100] + "..."
                results.append({"title": title, "link": link, "snippet": snippet})
    except Exception:
        pass

    # ------------------ 引擎 2: Sogou Fallback ------------------
    if not results:
        try:
            url_sogou = f"https://www.sogou.com/web?query={urllib.parse.quote(query)}"
            headers_sogou = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            resp = requests.get(url_sogou, headers=headers_sogou, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                items = soup.select('.results > div')
                for item in items:
                    if len(results) >= max_results: break
                    title_tag = item.select_one('h3 a')
                    if not title_tag: continue
                    title = title_tag.get_text(strip=True)
                    link = title_tag.get('href')
                    if not link or link.startswith('/'):
                        if link and link.startswith('/link?'):
                            link = "https://www.sogou.com" + link
                        else:
                            continue
                    snippet_div = item.select_one('.text-layout') or item.select_one('.ft') or item.select_one('p')
                    snippet = snippet_div.get_text(strip=True) if snippet_div else "点击查看详情"
                    results.append({"title": title, "link": link, "snippet": snippet})
        except Exception:
            pass

    if not results:
        results.append({"title": "未搜索到结果", "link": "#",
                        "snippet": "主要搜索引擎均未返回有效数据，请尝试更简单的关键词或检查网络。"})

    return results


# ------------------------------------------------------------
# 核心 Chat 接口
# ------------------------------------------------------------
@router.post("/chat")
async def chat(
        req: ChatRequest,
        x_user_id: Optional[str] = Header(default=None),
        x_session_id: Optional[str] = Header(default=None),
):
    stream_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    def _stream(gen, media_type: str = "application/x-ndjson"):
        return StreamingResponse(gen, media_type=media_type, headers=stream_headers)

    def _should_flush(
            buf: str,
            min_chars: int = 8,
            max_chars: int = 64,
            immediate: bool = False,
    ) -> bool:
        if immediate:
            return bool(buf)
        if len(buf) >= max_chars:
            return True
        if len(buf) >= min_chars:
            if "\n" in buf:
                return True
            if buf.endswith(("\n", "。", "！", "？", ".", "!", "?", "…")):
                return True
        return False

    def _make_text_buffer(min_chars: int = 8, max_chars: int = 64, immediate: bool = False):
        buf = ""

        def push(text: str) -> Optional[str]:
            nonlocal buf
            if not text:
                return None
            if immediate:
                return text
            buf += text
            if _should_flush(buf, min_chars, max_chars, immediate=immediate):
                out = buf
                buf = ""
                return out
            return None

        def flush() -> Optional[str]:
            nonlocal buf
            if immediate:
                return None
            if buf:
                out = buf
                buf = ""
                return out
            return None

        return push, flush

    def _split_text(text: str, size: int = 32) -> List[str]:
        if not text:
            return []
        if len(text) <= size:
            return [text]
        return [text[i:i + size] for i in range(0, len(text), size)]

    # 1. 基础参数解析
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(422, "message 不能为空")

    user_id = (req.user_id or x_user_id or "anonymous").strip()
    session_id = (req.session_id or x_session_id or str(uuid4())).strip()

    # 获取模型后端设置
    model_backend = req.model_backend or "local"
    model_id = (req.modelId or "").strip()

    mode = _normalize_mode(req.mode)
    # Hard guard: when meeting model is selected, force meeting mode to avoid accidental RAG routing.
    if mode == "general" and model_id == "1":
        mode = "meeting"
        print("🔒 [Router] Force mode -> meeting (modelId=1)")
    context_content = _truncate_context(req.context_content)
    personalization = _normalize_personalization(req.personalization)
    personalization_system_prompt = _build_personalization_system_prompt(personalization)
    _maybe_append_context_event(
        user_id=user_id,
        session_id=session_id,
        mode=mode,
        model_id=model_id,
        model_backend=model_backend,
        context_content=context_content,
        personalization=personalization,
    )

    print(f"🚀 [Chat] New Request: User={user_id}, Session={session_id}, Mode={mode}, Backend={model_backend}")

    shared_context_cache: Dict[str, Dict[str, str]] = {}

    def _get_shared_context(target_mode: Optional[str] = None, history_limit: int = FAST_CHAT_HISTORY_LIMIT) -> Dict[str, str]:
        normalized_mode = (target_mode or mode or "general").strip().lower() or "general"
        cache_key = f"{normalized_mode}:{history_limit}"
        cached = shared_context_cache.get(cache_key)
        if cached is not None:
            return cached

        history_text = _get_plain_history(
            user_id,
            session_id,
            limit=history_limit,
            mode=normalized_mode,
        )
        active_context = (context_content or "").strip()

        summary_context = ""
        try:
            hub = ContextHub(
                user_id=user_id,
                session_id=session_id,
                query=message,
                active_context_content=active_context,
                ui_mode=normalized_mode
            )
            if memory_summary:
                history_msgs = _get_langchain_history(
                    user_id,
                    session_id,
                    limit=max(6, history_limit),
                    mode=normalized_mode,
                )
                if history_msgs:
                    hub.history_summary = memory_summary.update_from_messages(
                        user_id=user_id,
                        session_id=session_id,
                        current_summary=hub.history_summary,
                        messages=history_msgs,
                        model_type=model_backend,
                    )
            if not hub.history_summary and history_text:
                hub.history_summary = history_text[:800]
            summary_context = hub.get_combined_context(max_len=2000)
        except Exception:
            summary_context = ""

        session_state = ""
        try:
            compaction_payload = _maybe_compact_context(
                user_id=user_id,
                session_id=session_id,
                mode=normalized_mode,
                model_backend=model_backend,
            )
            session_state = _build_compaction_context_block(compaction_payload)
        except Exception:
            session_state = ""

        bundle = {
            "history_text": history_text or "",
            "summary_context": summary_context or "",
            "session_state": session_state or "",
            "active_context": active_context or "",
        }
        shared_context_cache[cache_key] = bundle
        return bundle

    def _wrap_prompt_with_shared_context(
            base_prompt: str,
            shared_ctx: Dict[str, str],
            user_message: Optional[str] = None,
            recent_history: Optional[str] = None,
    ) -> str:
        merged_summary = (base_prompt or "").strip()
        summary_ctx = (shared_ctx.get("summary_context") or "").strip()
        if summary_ctx:
            merged_summary = f"{summary_ctx}\n\n{merged_summary}" if merged_summary else summary_ctx
        return _build_cache_friendly_prompt(
            user_message=(user_message if user_message is not None else message),
            session_state=shared_ctx.get("session_state", ""),
            summary_context=merged_summary,
            recent_history=(recent_history if recent_history is not None else shared_ctx.get("history_text", "")),
        )

    # --------------------------------------------------------
    # ✅ 联网搜索模式：ChatGPT 逻辑 (优化搜索词 -> 搜索 -> 思考 -> 回答)
    # --------------------------------------------------------
    async def fast_chat_response_generator(func_type: str = "chat", return_mode: str = "chat"):
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)
        try:
            active_mode = (return_mode or func_type or mode or "chat")
            shared_ctx = _get_shared_context(active_mode, history_limit=FAST_CHAT_HISTORY_LIMIT)
            system_prompt = _merge_system_prompt(None, personalization_system_prompt)
            prompt = _wrap_prompt_with_shared_context(
                "",
                shared_ctx,
                user_message=message,
            )

            for chunk in ask_llm_stream(
                prompt,
                system_prompt=system_prompt,
                model_type=model_backend,
            ):
                if chunk:
                    full_reply += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "user", "content": message, "func_type": func_type
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "assistant", "content": full_reply, "func_type": func_type
                    }).execute()
                except Exception as e:
                    print(f" History save failed: {e}")

            yield json.dumps({"t": "m", "sid": session_id, "mode": return_mode, "end": True}, ensure_ascii=False) + "\n"
        except Exception as e:
            print(f" [Chat Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"Error: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": return_mode, "end": True}, ensure_ascii=False) + "\n"

    def _is_doc_query(text: str) -> bool:
        t = (text or "").lower()
        keywords = ["doc", "document", "pdf", "ppt", "excel", "word", "attachment", "upload", "file", "wendang", "wenjian", "fujian", "shangchuan"]
        return any(k in t for k in keywords)

    def _is_weather_query(text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ["天气", "气温", "温度", "weather"])

    def _is_stock_query(text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ["股票", "股价", "行情", "stock", "price", "涨跌"])

    def _is_report_write_prompt(text: str) -> bool:
        t = text or ""
        return any(tag in t for tag in ["[指令:生成报告]", "[指令:生成PPT]", "[指令:起草邮件]"])

    def _extract_city(text: str, history: str = "") -> str:
        candidates = []
        for src in [text, history]:
            if not src:
                continue
            m = re.search(r"([\u4e00-\u9fa5]{2,6})\s*(天气|气温|温度)", src)
            if m:
                candidates.append(m.group(1))
            m2 = re.search(r"在([\u4e00-\u9fa5]{2,6})", src)
            if m2:
                candidates.append(m2.group(1))
        return candidates[0] if candidates else "北京"

    def _normalize_stock_query(text: str) -> str:
        if not text:
            return ""
        q = text.replace("股票", "").replace("股价", "").replace("行情", "").replace("价格", "").strip()
        return q or text

    async def search_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply_clean = ""

        try:
            # === Step 1: 智能生成搜索词 (Query Optimization) ===
            shared_ctx = _get_shared_context("search", history_limit=4)
            history_text = shared_ctx.get("history_text", "")
            summary_text = (shared_ctx.get("summary_context", "") or "").strip()[:1200]
            active_text = (shared_ctx.get("active_context", "") or "").strip()[:1000]

            yield json.dumps({"t": "c", "v": "> 🤔 正在规划搜索策略...\n\n"}, ensure_ascii=False) + "\n"

            # 调用 LLM 生成搜索词，要求生成 JSON 或特定格式以便提取主词和备选词
            query_gen_prompt = f"""请根据以下对话历史和用户最新问题，生成搜索关键词。
要求：
1. 输出格式为：主搜索词 | 备选搜索词
2. 如果用户问题包含代词，请替换为具体名称。
3. 主搜索词要精准，备选搜索词可以宽泛或尝试不同角度。
4. 只输出一行，用 "|" 分隔。

对话历史：
{history_text}

会话摘要：
{summary_text or "（无）"}

当前附加上下文：
{active_text or "（无）"}

用户最新问题：
{message}

搜索词："""

            is_weather_intent = _is_weather_query(message)
            is_stock_intent = _is_stock_query(message)

            raw_queries = ""
            alt_query = None
            if not is_weather_intent and not is_stock_intent:
                # Keep current backend while generating query with fast model fallback.
                for chunk in ask_llm_stream(query_gen_prompt, model_type=model_backend):
                    if chunk:
                        raw_queries += chunk

                raw_queries = raw_queries.strip().replace('"', '').replace("'", "")
                parts = [p.strip() for p in raw_queries.split('|') if p.strip()]

                main_query = parts[0] if parts else message
                alt_query = parts[1] if len(parts) > 1 else None
                search_query = main_query
            else:
                if is_weather_intent:
                    city = _extract_city(message, history_text)
                    search_query = f"{city} 天气"
                else:
                    search_query = _normalize_stock_query(message)
            # === Step 2: 执行搜索 (支持自动重试) ===

            # 简单判断是否是结构化意图
            status_icon = "🔍"
            if is_weather_intent or ("天气" in search_query):
                status_icon = "☁️"
            elif is_stock_intent or ("股价" in search_query):
                status_icon = "📈"

            search_results = []
            final_used_query = search_query

            # --- 第一轮搜索 ---
            yield json.dumps({"t": "c", "v": f"> {status_icon} 正在搜索：**{search_query}** ...\n\n"},
                             ensure_ascii=False) + "\n"
            raw_results = perform_web_search(search_query)

            # --- 结果打分与过滤 ---
            # 如果是 API 返回的（包含 title/link），进行打分
            valid_raw_results = [r for r in raw_results if r['link'] != '#']

            # 只有当结果数量足够且不是特定的工具结果（如天气）时，才应用严格打分
            is_tool_result = any("天气" in r['title'] or "行情" in r['title'] for r in valid_raw_results)

            if not is_tool_result and valid_raw_results:
                ranked = _rank_search_results(valid_raw_results, search_query)
                # 【新增逻辑】如果过滤太狠导致没结果了，就用原始结果的前3条兜底
                if not ranked and valid_raw_results:
                    print("⚠️ [Search] 过滤后无结果，启用兜底策略")
                    search_results = valid_raw_results[:3]
                else:
                    search_results = ranked
            else:
                search_results = valid_raw_results  # 工具结果或无结果直接用

            # --- 低质量/无结果自动重试 ---
            # 如果打分后的结果太少，且有备选词，尝试第二轮
            if len(search_results) < 2 and alt_query and not is_tool_result:
                yield json.dumps({"t": "c", "v": f"> 🔄 初步结果相关度低，尝试备选词：**{alt_query}** ...\n\n"},
                                 ensure_ascii=False) + "\n"

                raw_results_2 = perform_web_search(alt_query)
                valid_raw_results_2 = [r for r in raw_results_2 if r['link'] != '#']
                ranked_results_2 = _rank_search_results(valid_raw_results_2, alt_query)

                # 合并结果 (简单的追加，也可以根据分数混合)
                # 使用字典去重
                merged_map = {r['link']: r for r in search_results}
                for r in ranked_results_2:
                    if r['link'] not in merged_map:
                        merged_map[r['link']] = r

                # 重新转回列表并按分数排序
                search_results = list(merged_map.values())
                search_results.sort(key=lambda x: x.get("_score", 0), reverse=True)
                final_used_query = f"{search_query} / {alt_query}"

            # === Step 3: 阅读结果 ===
            valid_results = [r for r in search_results if r['link'] != '#']
            result_count = len(valid_results)

            if result_count == 0:
                yield json.dumps({"t": "c", "v": "> ⚠️ 未找到相关结果，尝试直接回答...\n\n"}, ensure_ascii=False) + "\n"
            else:
                yield json.dumps({"t": "c", "v": f"> 📄 已筛选出 {len(valid_results)} 个优质来源，正在阅读...\n\n"},
                                 ensure_ascii=False) + "\n"

            # 推送来源元数据给侧边栏 (JSON Object, Frontend renders link)
            srcs = []
            for r in valid_results:
                link = r.get("link", "")
                try:
                    domain = urllib.parse.urlparse(link).netloc.replace('www.', '')
                except:
                    domain = "Web"
                title = r.get("title", "Source")
                srcs.append({"title": title, "link": link, "domain": domain})

            if srcs:
                yield json.dumps({"t": "m", "sid": session_id, "src": srcs}, ensure_ascii=False) + "\n"

            # === Step 4: 组装最终回答 Prompt ===
            context_text = ""
            for i, res in enumerate(valid_results):
                # 提示包含来源的权威性信息（可选，让 LLM 知道这是官方来源）
                source_tag = ""
                if any(d in res.get('link', '') for d in HIGH_VALUE_DOMAINS):
                    source_tag = "[权威/官方来源] "

                context_text += f"【来源 {i + 1}】{source_tag}\n标题: {res.get('title')}\n链接: {res.get('link')}\n摘要: {res.get('snippet')}\n\n"

            if not context_text:
                context_text = "（搜索引擎未返回有效结果，请基于你的通用知识回答）"

            if is_tool_result and (is_weather_intent or is_stock_intent):
                prompt = f"""You are an assistant. Answer ONLY using the realtime results below.

User Question:
{message}

Realtime Results:
{context_text}

Requirements:
1) Use only facts present in the results; do not fabricate
2) If results are insufficient, say so explicitly
3) Do not output any links
4) Keep it concise and structured (Markdown)

Answer:
"""
            else:
                prompt = f"""You are an assistant. Answer based on the web search results below.

User Question:
{message}

Search Keywords:
{final_used_query}

Web Results:
{context_text}

Requirements:
1) Cite sources with [1] style markers
2) Do NOT include http links in the answer body
3) If results are irrelevant/empty, say so and answer from general knowledge
4) Use Markdown for clear structure
5) Prefer official/authoritative sources when present

Answer:
"""
            prompt = _wrap_prompt_with_shared_context(
                prompt,
                shared_ctx,
                user_message=message,
                recent_history=history_text,
            )

# === Step 5: 流式输出回答 ===
            # DB 模式更强调“快出字”，合并阈值更小
            push_chunk, flush_chunk = _make_text_buffer(min_chars=1, max_chars=32)
            for chunk in ask_llm_stream(
                prompt,
                system_prompt=personalization_system_prompt,
                model_type=model_backend,
            ):
                if chunk:
                    full_reply_clean += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            # === Step 6: 保存历史记录 (只保存纯净回答) ===
            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "user", "content": message, "func_type": "search"
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "assistant", "content": full_reply_clean, "func_type": "search"
                    }).execute()
                except Exception as e:
                    print(f"⚠️ History save failed: {e}")

            yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [Search Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"\n❌ 搜索模式处理错误: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"

    # --------------------------------------------------------
    # ✅ 数据库模式：完全绕过 langgraph_agent，直接执行 database_manager
    # --------------------------------------------------------
    async def database_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply = ""
        try:
            shared_ctx = _get_shared_context("database", history_limit=6)
            # 来源：先发数据库信息，后续收到 SQL 事件后会追加
            db_sources: List[Dict[str, Any]] = [{
                "type": "database",
                "title": f"数据库：{DEFAULT_DB_NAME}",
                "name": DEFAULT_DB_NAME,
            }]
            yield json.dumps({"t": "m", "sid": session_id, "src": db_sources}, ensure_ascii=False) + "\n"

            # ✅ 修复：传递 model_type 参数给 query_fast
            push_chunk, flush_chunk = _make_text_buffer(immediate=True)
            for event in db_manager.query_fast(
                DEFAULT_DB_NAME,
                message,
                model_type=model_backend,
                response_instruction=personalization_system_prompt,
                history_context=shared_ctx.get("history_text", ""),
                summary_context=shared_ctx.get("summary_context", ""),
                session_state=shared_ctx.get("session_state", ""),
                active_context_content=shared_ctx.get("active_context", ""),
            ):
                if isinstance(event, dict) and event.get("type") == "status":
                    status_msg = event.get("message")
                    if status_msg:
                        yield json.dumps({"t": "m", "sid": session_id, "status": status_msg}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)
                    continue
                if isinstance(event, dict) and event.get("type") == "source":
                    source_item = event.get("source")
                    if isinstance(source_item, dict) and source_item:
                        db_sources.append(source_item)
                        yield json.dumps({"t": "m", "sid": session_id, "src": db_sources}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)
                    continue
                chunk = event
                if chunk:
                    full_reply += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            # 保存历史记录
            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": message,
                        "func_type": "database"
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": full_reply,
                        "func_type": "database"
                    }).execute()
                except Exception as e:
                    print(f"⚠️ History save failed: {e}")

            yield json.dumps({"t": "m", "sid": session_id, "mode": "database", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [DB Mode Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\n❌ 数据库模式处理错误: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "database", "end": True}, ensure_ascii=False) + "\n"

    # --------------------------------------------------------
    # ✅ 审计模式 (Audit Mode)：直连 Audit Service
    # --------------------------------------------------------
    async def audit_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if not run_audit_pipeline:
            yield json.dumps({"t": "c", "v": "❌ Audit Service 未加载。"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"
            return

        full_reply = ""
        # 消息中可能包含 "Attached files..." 等前缀，Audit Service 内部有 normalize 步骤
        # 这里直接传 raw message 即可
        try:
            shared_ctx = _get_shared_context("audit", history_limit=6)
            audit_message = message
            ctx_parts: List[str] = []
            if shared_ctx.get("session_state"):
                ctx_parts.append(f"[会话状态]\n{shared_ctx['session_state'][:1200]}")
            if shared_ctx.get("summary_context"):
                ctx_parts.append(f"[摘要上下文]\n{shared_ctx['summary_context'][:1200]}")
            if shared_ctx.get("history_text"):
                ctx_parts.append(f"[近期对话]\n{shared_ctx['history_text'][:1200]}")
            if shared_ctx.get("active_context"):
                ctx_parts.append(f"[当前附加上下文]\n{shared_ctx['active_context'][:1000]}")
            if ctx_parts:
                audit_message = f"{message}\n\n[审计补充上下文]\n" + "\n\n".join(ctx_parts)

            # ✅ 传递 model_type
            push_chunk, flush_chunk = _make_text_buffer()
            async for chunk in run_audit_pipeline(user_id, session_id, audit_message, model_type=model_backend):
                if chunk:
                    full_reply += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            # 审计结果（audit_runs）的保存已在 Service 内部完成，这里只保存对话记录
            if user_id != "anonymous":
                sb = require_supabase()
                sb.table("history").insert({
                    "user_id": user_id, "session_id": session_id,
                    "role": "user", "content": message, "func_type": "audit"
                }).execute()
                sb.table("history").insert({
                    "user_id": user_id, "session_id": session_id,
                    "role": "assistant", "content": full_reply, "func_type": "audit"
                }).execute()

            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [Audit Mode Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\n❌ 审计模式处理错误: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"


    # --------------------------------------------------------
    # ✅ 文档模式（RAG 直连）：不走 langgraph，只用检索 + LLM
    # --------------------------------------------------------
    async def rag_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if search_user_documents is None:
            yield json.dumps({"t": "c", "v": "❌ 文档检索模块未加载，无法使用文档模式（RAG）。"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"
            return

        full_reply = ""
        try:
            shared_ctx = _get_shared_context("rag", history_limit=6)
            # 1) 检索
            summary_intent = bool(re.search(r"(总结|概述|摘要|提炼|梳理|归纳)", message))
            docs = search_user_documents(
                user_id,
                message,
                k=8 if summary_intent else 4,
                match_threshold=0.0 if summary_intent else 0.3
            )
            chunks, srcs = _to_text_and_sources(docs)
            # 控制 RAG 上下文长度，避免本地模型上下文窗口溢出导致空白回复
            normalized_chunks: List[str] = []
            for c in chunks:
                if not c:
                    continue
                t = str(c).strip()
                if not t:
                    continue
                normalized_chunks.append(t[:RAG_MAX_CHUNK_CHARS])
                if len(normalized_chunks) >= RAG_MAX_CHUNKS:
                    break
            chunks = normalized_chunks

            # 2) 给前端发来源（可选）
            if srcs:
                yield json.dumps({"t": "m", "sid": session_id, "src": srcs}, ensure_ascii=False) + "\n"
            else:
                yield json.dumps({"t": "m", "sid": session_id, "src": ["知识库检索结果"]}, ensure_ascii=False) + "\n"

            # 3) 组装 Prompt
            active = (shared_ctx.get("active_context", "") or "").strip()[:RAG_MAX_ACTIVE_CONTEXT_CHARS]
            kb_sections = []
            if active and (summary_intent or not chunks):
                kb_sections.append(f"【附件上下文】\n{active}")
            if chunks:
                kb_sections.extend([f"【片段{i + 1}】\n{c}" for i, c in enumerate(chunks)])

            kb_text = "\n\n".join(kb_sections) if kb_sections else "（未检索到相关资料）"
            if len(kb_text) > RAG_MAX_KB_TEXT_CHARS:
                kb_text = kb_text[:RAG_MAX_KB_TEXT_CHARS] + "\n\n[资料过长，已自动截断]"

            if not kb_sections:
                yield json.dumps({"t": "c", "v": "未检索到文档内容。请确认文档已成功上传并完成解析后再试。"}, ensure_ascii=False) + "\n"
                yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"
                return

            prompt = f"""你是一名企业知识库问答助手。请严格只基于【资料】回答用户问题：
- 如果资料不足以回答，就明确说“资料不足”，并告诉用户需要补充什么信息或上传什么文档。
- 不要编造任何不存在于资料中的事实。

【用户问题】
{message}

【资料】
{kb_text}

"""
            if active:
                prompt += f"""
【用户当前屏幕/附件上下文】
{active}
"""

            prompt += "\n请用中文给出清晰、专业、简洁的回答。\n"
            if summary_intent:
                prompt += "用户明确要求总结文档，请直接给出结构化摘要（核心主题+关键要点3-7条+结论/建议），不要追问。\n"
            prompt = _wrap_prompt_with_shared_context(
                prompt,
                shared_ctx,
                user_message=message,
            )
            print(
                f"📚 [RAG] summary={summary_intent}, chunks={len(chunks)}, prompt_chars={len(prompt)}, backend={model_backend}",
                flush=True
            )

            # 4) 流式输出
            # ✅ 使用 model_backend
            push_chunk, flush_chunk = _make_text_buffer(immediate=True)
            for chunk in ask_llm_stream(
                prompt,
                system_prompt=personalization_system_prompt,
                model_type=model_backend,
            ):
                if chunk:
                    full_reply += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)
            if not full_reply.strip():
                full_reply = "未收到模型生成内容（可能因为上下文过长或模型暂时无响应）。请重试，或切换到云端模型后再试。"
                yield json.dumps({"t": "c", "v": full_reply}, ensure_ascii=False) + "\n"
                await asyncio.sleep(0)

            # 5) 保存历史记录
            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": message,
                        "func_type": "rag"
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": full_reply,
                        "func_type": "rag"
                    }).execute()
                except Exception as e:
                    print(f"⚠️ History save failed: {e}")

            yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [RAG Mode Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\n❌ 文档模式处理错误: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"

    # --------------------------------------------------------
    # 默认：LangGraph 4-Layer 架构（通用/审单/其它）
    # --------------------------------------------------------
    async def langgraph_response_generator():
        # 发送会话元数据
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if not app_graph:
            err_msg = "❌ 系统错误：LangGraph 模块未加载。"
            yield json.dumps({"t": "c", "v": err_msg}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "error", "end": True}, ensure_ascii=False) + "\n"
            return

        # 2. 初始化 ContextHub (Layer 2 的数据基础)
        hub = ContextHub(
            user_id=user_id,
            session_id=session_id,
            query=message,
            active_context_content=req.context_content,
            ui_mode=mode
        )

        # 3. 准备 Graph 状态输入
        history_msgs = _get_langchain_history(user_id, session_id, mode=mode)

        initial_state = {
            "hub": hub,
            "messages": history_msgs,
            "intent": "chat",
            "agent_output": {},
            "final_response": "",
            "explain_steps": [],
            "sources": [],  # 初始化为空
            # ✅ 让图内也能知道用户选择的 mode / modelId（可选）
            "mode": mode,
            "modelId": req.modelId,
            # ✅ 传递 model_backend
            "model_backend": model_backend
        }

        full_reply_display = ""
        full_reply_clean = ""  # 只保存“最终回答”，不包含思考/工具日志
        final_intent = "general"

        try:
            # === 运行 LangGraph (Layer 1 -> Layer 4) ===
            print("⚙️ [Graph] Invoking 4-Layer Architecture...")

            # 同步调用 Graph，等待 Synthesizer 准备好最终 Prompt
            final_state = app_graph.invoke(initial_state)

            final_prompt = final_state.get("final_response", message)
            final_intent = final_state.get("intent", "general")
            explain_steps = final_state.get("explain_steps", [])
            sources = final_state.get("sources", [])
            compaction_payload = _maybe_compact_context(
                user_id=user_id,
                session_id=session_id,
                mode=mode,
                model_backend=model_backend,
            )
            session_state_text = _build_compaction_context_block(compaction_payload)
            recent_history_for_layout = _get_plain_history(
                user_id=user_id,
                session_id=session_id,
                limit=FAST_CHAT_HISTORY_LIMIT,
                mode=mode,
            )
            final_prompt = _build_cache_friendly_prompt(
                user_message=message,
                session_state=session_state_text,
                summary_context=final_prompt,
                recent_history=recent_history_for_layout,
            )

            # ✨ [新特性] 展示 Agent 思考过程 (Explainable AI)
            if explain_steps:
                steps_str = "\n".join([f"> 🧠 {step}" for step in explain_steps])
                yield json.dumps({"t": "c", "v": f"{steps_str}\n\n"}, ensure_ascii=False) + "\n"
                # 注意：思考过程只展示给前端，不写入历史，避免污染后续上下文
                full_reply_display += f"{steps_str}\n\n"

            # ✅ [修复] 如果有文档来源，发送给前端显示
            if sources:
                yield json.dumps({"t": "m", "sid": session_id, "src": sources}, ensure_ascii=False) + "\n"

            # === Layer 4 Output: 流式输出最终回答 ===
            print(f"💬 [Synthesizer] Streaming response for intent: {final_intent} using {model_backend}")

            # 使用用户选择的后端模型 (local / cloud)
            push_chunk, flush_chunk = _make_text_buffer()
            for chunk in ask_llm_stream(
                final_prompt,
                system_prompt=personalization_system_prompt,
                model_type=model_backend,
            ):
                if chunk:
                    full_reply_display += chunk
                    full_reply_clean += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            # === 保存历史记录 ===
            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "user", "content": message, "func_type": final_intent
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id, "session_id": session_id,
                        "role": "assistant", "content": full_reply_clean,
                        "func_type": final_intent,
                        # 可选：如果表支持 metadata，可以把 sources 存进去
                        # "metadata": {"sources": sources}
                    }).execute()
                except Exception as e:
                    print(f"⚠️ History save failed: {e}")

            # 发送结束元数据
            yield json.dumps(
                {"t": "m", "sid": session_id, "mode": final_intent, "end": True},
                ensure_ascii=False
            ) + "\n"

        except Exception as e:
            print(f"❌ [Graph Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\n❌ 系统处理错误: {str(e)}"}, ensure_ascii=False) + "\n"

    # 分发：手动模式强制只走对应功能
    is_report_write_mode = (model_id == "3") or _is_report_write_prompt(message)
    auto_routing_enabled = (mode == "general") and (not is_report_write_mode)
    is_doc_query = _is_doc_query(message) if auto_routing_enabled else False
    is_db_query = False
    if auto_routing_enabled and _is_db_question_by_tables:
        try:
            is_db_query = _is_db_question_by_tables(message)[0]
        except Exception:
            is_db_query = False

    if auto_routing_enabled and FAST_CHAT_DIRECT and not context_content and not is_doc_query and not is_db_query:
        return _stream(fast_chat_response_generator())

    # 🚀 Fast-path: auto-routed DB questions go straight to database mode (skip LangGraph + extra LLM)
    if auto_routing_enabled and is_db_query and not context_content and not is_doc_query:
        return _stream(database_response_generator())

    if mode == "database":
        return _stream(database_response_generator())
    if mode == "rag":
        return _stream(rag_response_generator())
    if mode == "search":
        return _stream(search_response_generator())
    if mode == "audit": # ✅ 新增 Audit 路由
        return _stream(audit_response_generator())

    if auto_routing_enabled:
        return _stream(langgraph_response_generator())

    return _stream(
        fast_chat_response_generator(func_type=mode, return_mode=mode),
        media_type="application/x-ndjson"
    )


# ------------------------------------------------------------
# 其他历史记录接口 (保持不变)
# ------------------------------------------------------------
@router.get("/history/sessions")
def get_sessions_api(user_id: str):
    return get_user_sessions(user_id)


@router.get("/history/{session_id}")
def get_session_messages_api(session_id: str, user_id: str):
    return get_history(user_id, session_id)


@router.delete("/history/{session_id}")
def delete_session_api(session_id: str, user_id: str, background_tasks: StreamingResponse):
    from fastapi import BackgroundTasks
    delete_session(user_id, session_id)
    return {"status": "ok"}


@router.patch("/history/{session_id}/title")
def rename_session_api(session_id: str, user_id: str, req: RenameRequest):
    success = rename_session(user_id, session_id, req.title)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to rename session")
    return {"status": "ok", "message": "Session renamed", "title": req.title}
