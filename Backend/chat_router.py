from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import os
import hashlib
import threading
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header, Request
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
from deepseek_llm import ask_llm_stream_async, ask_llm

# 引入我们新构建的模块（仅在 LangGraph 路径需要）
from context_hub import ContextHub

# ✅ 直接数据库查询：强制走 database_manager，不经过 langgraph
from database_manager import db_manager, DB_NAME as DEFAULT_DB_NAME, ALLOWED_TABLES

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
_ACTIVE_STREAM_CANCELS: Dict[str, threading.Event] = {}
_ACTIVE_STREAM_LOCK = threading.Lock()


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    user_id: Optional[str] = None
    session_id: Optional[str] = None

    # Frontend fields: mode / modelId
    mode: Optional[str] = Field(default="general", description="对话模式：general / database / rag / search / audit ...")
    modelId: Optional[str] = Field(default=None, description="Selected model ID from frontend")

    # New field: model backend selection
    model_backend: Optional[str] = Field(default="local", description="backend: local (Qwen) / cloud (DeepSeek)")

    # 上下文内容（OCR/会议/订单文本）
    context_content: Optional[str] = None
    # Explicit file list (reserved)
    files: List[str] = []
    personalization: Dict[str, Any] = Field(default_factory=dict)


class RenameRequest(BaseModel):
    title: str


# ------------------------------------------------------------
# Helper: sanitize history content
# ------------------------------------------------------------
def _sanitize_history_content(text: str) -> str:
    """Clean history text and remove tool/debug traces before prompting."""
    if text is None:
        return ""
    s = str(text)

    # Remove special tokens that may leak into history
    s = s.replace("<|im_start|>", "").replace("<|im_end|>", "")
    # 移除前端/中间层注入的 meta 行
    s = re.sub(r'^\s*Assistant:\s*\{.*?\}\s*$', '', s, flags=re.MULTILINE)
    # 移除 Explainable AI/工具思考日志
    s = re.sub(r'^\s*>\s*??.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*??.*$', '', s, flags=re.MULTILINE)

    # [New] remove search-process logs to avoid prompt contamination
    s = re.sub(r'^\s*>\s*??.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*??.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*??.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*??.*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\s*>\s*WEATHER.*$', '', s, flags=re.MULTILINE)  # weather status
    s = re.sub(r'^\s*>\s*STOCK.*$', '', s, flags=re.MULTILINE)  # stock status
    s = re.sub(r'^\s*>\s*RETRY.*$', '', s, flags=re.MULTILINE)  # retry status

    # 移除 ReAct 过程日志
    s = re.sub(r'^\s*ReAct\s*(思考|行动|观察).*$', '', s, flags=re.MULTILINE)
    # Remove generic debug banner lines
    s = re.sub(r'^\s*\[[A-Z_]+\].*$', '', s, flags=re.MULTILINE)
    # Collapse excessive blank lines
    s = re.sub(r'\n{3,}', '\n\n', s)

    return s.strip()


def _looks_like_meeting_minutes(text: str) -> bool:
    if not text:
        return False
    s = str(text)
    markers = [
        "浼氳涓婚",
        "关键决策",
        "行动项",
        "风险与待事项",
        "浼氳绾",
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


_QUERY_TERM_STOPWORDS = {
    "请问", "一个", "这个", "那个", "然后", "还有", "就是", "现在", "帮我", "我们",
    "what", "which", "about", "please", "thanks", "thank", "tell", "show", "give",
}


def _normalize_match_text(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _extract_query_terms(text: Optional[str], max_terms: int = 14) -> List[str]:
    raw = str(text or "").lower()
    terms: List[str] = []

    for zh_seq in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
        seq = zh_seq.strip()
        if not seq:
            continue
        if len(seq) <= 4:
            if seq not in _QUERY_TERM_STOPWORDS:
                terms.append(seq)
            continue

        # For long Chinese phrases, use n-grams so topic overlap can still be detected.
        for n in (4, 3, 2):
            for i in range(0, len(seq) - n + 1):
                t = seq[i:i + n]
                if t and t not in _QUERY_TERM_STOPWORDS:
                    terms.append(t)

    for t in re.findall(r"[a-z0-9_]{3,}", raw):
        if t and t not in _QUERY_TERM_STOPWORDS:
            terms.append(t)

    uniq: List[str] = []
    seen = set()
    for t in sorted(terms, key=len, reverse=True):
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
        if len(uniq) >= max_terms:
            break
    return uniq


def _is_context_related(query: Optional[str], candidate_text: Optional[str], min_hits: int = 1) -> bool:
    if not candidate_text:
        return False
    query_terms = _extract_query_terms(query)
    if not query_terms:
        return True

    normalized = _normalize_match_text(candidate_text)
    hits = 0
    for term in query_terms:
        if term in normalized:
            hits += 1
            if hits >= min_hits:
                return True
    return False


_FOLLOWUP_HINTS = [
    "这个", "那个", "这样", "那就", "继续", "然后", "按这个", "就按这个",
    "可以", "行", "好的", "嗯", "随便", "直接", "开始", "写吧", "你来", "就是",
]

_DIRECT_EXECUTION_HINTS = [
    "直接写", "你来写", "你来定", "自由发挥", "随便", "先出稿", "先写",
    "直接开始", "不要追问", "别问了", "不用问", "就按这个写", "你决定",
]

_WRITING_TASK_HINTS = [
    "作文", "文章", "写作", "写一篇", "文案", "报告", "发言稿", "邮件",
    "总结", "周报", "方案", "脚本", "提纲",
]


def _looks_like_followup_turn(text: Optional[str]) -> bool:
    q = _normalize_match_text(text)
    if not q:
        return False
    if len(q) <= 18 and any(k in q for k in _FOLLOWUP_HINTS):
        return True
    return bool(re.search(r"(??|??|??|??|??|??|??|??|??|??)", q))


def _should_force_direct_draft(user_text: Optional[str], history_text: Optional[str]) -> bool:
    q = _normalize_match_text(user_text)
    if not q:
        return False
    if not any(k in q for k in _DIRECT_EXECUTION_HINTS):
        return False
    h = _normalize_match_text(history_text)
    return any(k in q for k in _WRITING_TASK_HINTS) or any(k in h for k in _WRITING_TASK_HINTS)


def _pick_relevant_history_records(
        records: List[Dict[str, Any]],
        query: Optional[str],
        limit: int,
        mode: Optional[str],
) -> List[Dict[str, Any]]:
    if not records:
        return []

    current_mode = (mode or "").strip().lower()
    scope = max(limit * 3, limit)
    candidate_records = records[-scope:]
    query_terms = _extract_query_terms(query, max_terms=10)
    query_has_signal = bool(query_terms)
    is_followup_turn = _looks_like_followup_turn(query)
    min_hits = 2 if len(query_terms) >= 5 else 1
    keep_tail_count = 3 if is_followup_turn else 2

    selected_rev: List[Dict[str, Any]] = []
    for idx, r in enumerate(reversed(candidate_records)):
        raw_role = (r.get("role") or "").strip().lower()
        if raw_role == "meta":
            continue

        content = _sanitize_history_content(r.get("content"))
        if not content:
            continue

        raw_func_type = (r.get("func_type") or "").strip().lower()
        if current_mode != "meeting" and raw_func_type == "meeting":
            continue
        if current_mode != "meeting" and raw_role == "assistant" and _looks_like_meeting_minutes(content):
            continue

        keep_latest = len(selected_rev) < keep_tail_count
        related = _is_context_related(query, content, min_hits=min_hits)
        same_mode_recent = bool(
            (is_followup_turn or (not query_has_signal))
            and current_mode
            and raw_func_type == current_mode
            and idx < 4
        )
        fallback_same_mode = bool((not query_has_signal) and current_mode and raw_func_type == current_mode)

        if keep_latest or related or same_mode_recent or fallback_same_mode:
            selected_rev.append(r)
            if len(selected_rev) >= limit:
                break

    return list(reversed(selected_rev))


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


def _get_plain_history(
        user_id: str,
        session_id: str,
        limit: int = 4,
        mode: Optional[str] = None,
        query: Optional[str] = None,
) -> str:
    """Get plain text history for LLM context, with lightweight relevance filtering."""
    if user_id == "anonymous":
        return ""
    try:
        records = get_history_limited(user_id, session_id, limit=max(limit * 3, limit))
        recent = _pick_relevant_history_records(records, query=query, limit=limit, mode=mode)
        history_str = ""
        for r in recent:
            raw_role = (r.get("role") or "").strip().lower()
            if raw_role == "user":
                role = "User"
            elif raw_role == "assistant":
                role = "Assistant"
            elif raw_role == "context":
                role = "Context"
            else:
                role = "Assistant"

            content = _sanitize_history_content(r.get("content"))
            if content:
                history_str += f"{role}: {content}\n"
        return history_str
    except Exception:
        return ""


def _get_langchain_history(
        user_id: str,
        session_id: str,
        limit: int = 6,
        mode: Optional[str] = None,
        query: Optional[str] = None,
):
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    if user_id == "anonymous":
        return []
    try:
        records = get_history_limited(user_id, session_id, limit=max(limit * 3, limit))
        filtered_records = _pick_relevant_history_records(records, query=query, limit=limit, mode=mode)
        messages = []
        for r in filtered_records:
            role = r.get("role")
            content = _sanitize_history_content(r.get("content"))
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role == "context":
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


_DB_INTENT_ACTION_WORDS = [
    "sql", "database", "table", "select", "where", "join", "groupby", "count", "sum",
    "数据库", "数据表", "表里", "查询", "查", "查下", "查找", "统计", "汇总", "筛选", "排序", "排名", "明细",
    "多少", "总额", "总数", "占比",
]

_DB_INTENT_ENTITY_WORDS = [
    "订单", "客户", "员工", "库存", "供应商", "采购", "产品", "商品", "部门", "角色", "公司",
    "orders", "customers", "employees", "inventory", "suppliers", "purchases", "products", "departments",
]


def _looks_like_db_request(text: str) -> bool:
    q = _normalize_match_text(text)
    if not q:
        return False

    # Direct table-name hit from whitelist.
    for table_name in ALLOWED_TABLES:
        if table_name.lower() in q:
            return True

    has_action = any(k in q for k in _DB_INTENT_ACTION_WORDS)
    has_entity = any(k in q for k in _DB_INTENT_ENTITY_WORDS)
    if has_action and has_entity:
        return True

    # Raw SQL pattern
    if re.search(r"\bselect\b.*\bfrom\b", q):
        return True

    return False


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
        or "unknown_source"
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
    """Normalize retrieved document items into plain texts and source metadata."""
    texts: list[str] = []
    srcs: list[Dict[str, Any]] = []
    if not items:
        return texts, srcs

    for it in items:
        if it is None:
            continue
        # Save short-term snapshot
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

        # Build compact shared context
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
# Search relevance scoring helpers
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
    """Calculate a relevance score for one search result."""
    score = 0.0
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    link = result.get("link", "").lower()

    # 1. Title keyword boost
    for kw in query_keywords:
        kw = kw.lower()
        if kw in title:
            score += 3.0  # 标题包含关键词权重高
        if kw in snippet:
            score += 1.0  # 摘要包含关键词

    # 2. Domain credibility boost
    domain_boost = False
    for domain in HIGH_VALUE_DOMAINS:
        if domain in link:
            score += 5.0  # High-trust domain gets stronger weight
            domain_boost = True
            break

    # 3. Low-value domain penalty
    if not domain_boost:
        for domain in LOW_VALUE_DOMAINS:
            if domain in link:
                score -= 2.0

    # 4. Very short snippet penalty
    if len(snippet) < 20:
        score -= 5.0

    return score


def _rank_search_results(results: List[dict], query: str, min_score: float = 3.0) -> List[dict]:
    """Rank and filter search results by relevance."""
    if not results:
        return []

    # Tokenize query for relevance scoring
    # Fallback to full query if tokenization is empty
    keywords = [k for k in query.split() if len(k) > 1]
    if not keywords:
        keywords = [query]

    scored_results = []
    for r in results:
        score = _calculate_result_score(r, keywords)
        # Persist intermediate relevance score
        r["_score"] = score
        if score >= min_score:
            scored_results.append(r)

    # Sort by score descending
    scored_results.sort(key=lambda x: x["_score"], reverse=True)

    return scored_results


# ------------------------------------------------------------
# Weather tool API
# ------------------------------------------------------------
def tool_get_weather(city_name: str) -> List[dict]:
    """Get weather information from wttr.in."""
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
    """Get stock quote information."""
    import requests
    results = []
    print(f"📈 [Stock Tool] Analyzing query: {query}")
    try:
        # 1. 简单的正则匹配股票代码 (支持 sh/sz/hk/us)
        # 如果用户输入 "贵州茅台股价"，这里需要先有一个 Search 步骤去换取代码，
        # If market prefix is missing, call suggest first
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
        # 这里做一个简化策略：如果包含中文，先去 suggest 接口拿代码
                data = match.group(1).split(',')
                # data[3] 通常是带市场前缀的代码 (e.g. sh600519)
                stock_code = data[3]
                stock_name = data[0]

        if stock_code:
            # 2. 閼惧嘲褰囩€圭偞妞傜悰灞惧剰
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
                            "title": f"{stock_name} ({stock_code}) Realtime Quote",
                            "link": f"https://finance.sina.com.cn/realstock/company/{stock_code}/nc.shtml",
                            "snippet": f"当前价格: ¥{price}\n涨跌幅: {percent:.2f}%\n涨跌额: {change:.2f}\n今开: {open_p} | 最高: {high} | 最低: {low}\n时间: {date} {time}"
                        })
                    elif len(vals) > 5:  # 美股/港股格式略有不同，做简单容错
                        price = vals[1] if len(vals) > 1 else "N/A"
                        results.append({
                            "title": f"{stock_name} ({stock_code}) Realtime Quote",
                            "link": f"https://finance.sina.com.cn",
                            "snippet": f"最新价: {price} (fallback quote)"
                        })

    except Exception as e:
        print(f"⚠️ [Stock Tool] Failed: {e}")

    return results


# ------------------------------------------------------------
# Search tool: prefer official API, fallback to scraping
# ------------------------------------------------------------
def perform_web_search(query: str, max_results: int = 8) -> List[dict]:
    """
    Smart web search routing:
    1. Intent tools (weather/stock) when applicable
    2. Bing API (if key exists)
    3. SerpAPI (if key exists)
    4. Fallback scraping
    """
    results = []

    # --- 1. Try direct tools first (weather / stock) ---
    q_lower = query.lower()
    if "天气" in q_lower or "weather" in q_lower or "气温" in q_lower:
        # Invoke registered tool (tool)
        # Normalize query before parsing
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
                return results  # Success: return immediately
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
    """Fallback HTML scraping search implementation."""
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
                    snippet = snippet_div.get_text(strip=True) if snippet_div else "No snippet"
                    results.append({"title": title, "link": link, "snippet": snippet})
        except Exception:
            pass

    if not results:
        results.append({
            "title": "No search results",
            "link": "#",
            "snippet": "Primary search engines returned no valid results. Try simpler keywords or check network.",
        })

    return results


# ------------------------------------------------------------
# 核心 Chat 接口
# ------------------------------------------------------------
# Fixed identity reply for creator/model questions.
IDENTITY_FIXED_REPLY = "我是由浅夏安然创造的imagine agent，是你的办公小助手，感谢使用。"

_IDENTITY_CN_PATTERNS = [
    r"你是谁",
    r"你是.*(创造|开发|构建|训练).*的",
    r"(谁|谁在).*?(创造|开发|构建|训练).*你",
    r"你(用的|是什么|属于)?什么模型",
    r"你的模型(是|叫)?什么",
    r"你是(chatgpt|gpt|qwen|deepseek)吗",
]

_IDENTITY_EN_PATTERNS = [
    r"who(created|made|built|developed)you",
    r"whoareyou",
    r"what(model|llm)areyou",
    r"whichmodelareyou",
    r"whatisyourmodel",
]


def _is_identity_profile_question(text: str) -> bool:
    if not text:
        return False

    normalized = re.sub(r"\s+", "", str(text)).lower()
    for pattern in _IDENTITY_CN_PATTERNS:
        if re.search(pattern, normalized):
            return True
    for pattern in _IDENTITY_EN_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False


@router.post("/chat")
async def chat(
        req: ChatRequest,
        request: Request,
        x_user_id: Optional[str] = Header(default=None),
        x_session_id: Optional[str] = Header(default=None),
):
    stream_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    cancel_state = {"cancelled": False, "logged": False}
    cancel_event = threading.Event()
    stream_key = ""
    _ITER_DONE = object()

    def _unregister_active_stream():
        if not stream_key:
            return
        with _ACTIVE_STREAM_LOCK:
            current_event = _ACTIVE_STREAM_CANCELS.get(stream_key)
            if current_event is cancel_event:
                _ACTIVE_STREAM_CANCELS.pop(stream_key, None)

    def _mark_cancelled():
        if cancel_state["cancelled"] and cancel_event.is_set():
            return
        cancel_state["cancelled"] = True
        cancel_event.set()
        if not cancel_state["logged"]:
            cancel_state["logged"] = True
            print("[Chat] Client disconnected, cancel streaming response.")

    def _is_cancelled() -> bool:
        return bool(cancel_state["cancelled"] or cancel_event.is_set())

    async def _check_client_disconnected() -> bool:
        if cancel_event.is_set():
            cancel_state["cancelled"] = True
            return True
        if cancel_state["cancelled"]:
            return True
        try:
            if await request.is_disconnected():
                _mark_cancelled()
        except Exception:
            pass
        return bool(cancel_state["cancelled"] or cancel_event.is_set())

    def _close_iterator(iterator: Any):
        close_fn = getattr(iterator, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass

    def _next_or_done(iterator):
        try:
            return next(iterator)
        except StopIteration:
            return _ITER_DONE

    async def _iter_sync_stream(sync_iter):
        iterator = iter(sync_iter)
        try:
            while True:
                if await _check_client_disconnected():
                    break
                item = await asyncio.to_thread(_next_or_done, iterator)
                if item is _ITER_DONE:
                    break
                if await _check_client_disconnected():
                    break
                yield item
        except asyncio.CancelledError:
            _mark_cancelled()
            raise
        finally:
            _close_iterator(iterator)

    async def _disconnect_aware_stream(gen):
        try:
            async for item in gen:
                if await _check_client_disconnected():
                    break
                yield item
        except asyncio.CancelledError:
            _mark_cancelled()
            raise
        finally:
            aclose_fn = getattr(gen, "aclose", None)
            if callable(aclose_fn):
                try:
                    await aclose_fn()
                except Exception:
                    pass
            _unregister_active_stream()

    def _stream(gen, media_type: str = "application/x-ndjson"):
        return StreamingResponse(_disconnect_aware_stream(gen), media_type=media_type, headers=stream_headers)

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

    # 1. Request validation
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(422, "message 不能为空")

    user_id = (req.user_id or x_user_id or "anonymous").strip()
    session_id = (req.session_id or x_session_id or str(uuid4())).strip()
    stream_key = f"{user_id}:{session_id}"

    previous_event = None
    with _ACTIVE_STREAM_LOCK:
        previous_event = _ACTIVE_STREAM_CANCELS.get(stream_key)
        _ACTIVE_STREAM_CANCELS[stream_key] = cancel_event
    if previous_event and previous_event is not cancel_event:
        previous_event.set()
        print(f"[Chat] Cancel previous in-flight stream for {stream_key}")

    # 閼惧嘲褰囧Ο鈥崇€烽崥搴ｇ拋鍓х枂
    model_backend = req.model_backend or "local"
    model_id = (req.modelId or "").strip()

    mode = _normalize_mode(req.mode)
    # Hard guard: when meeting model is selected, force meeting mode to avoid accidental RAG routing.
    if mode == "general" and model_id == "1":
        mode = "meeting"
        print("🔒 [Router] Force mode -> meeting (modelId=1)")
    if _is_identity_profile_question(message):
        async def fixed_identity_response_generator():
            yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "c", "v": IDENTITY_FIXED_REPLY}, ensure_ascii=False) + "\n"

            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": message,
                        "func_type": "identity",
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": IDENTITY_FIXED_REPLY,
                        "func_type": "identity",
                    }).execute()
                except Exception as e:
                    print(f"Identity reply history save failed: {e}")

            yield json.dumps({"t": "m", "sid": session_id, "mode": mode, "end": True}, ensure_ascii=False) + "\n"

        return _stream(fixed_identity_response_generator())

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
            query=message,
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
                    query=message,
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
            if summary_context and not _is_context_related(message, summary_context, min_hits=1):
                # Drop stale summary context when the topic has shifted.
                summary_context = ""
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
    # Fast fallback path: Chat mode without Graph
    # --------------------------------------------------------
    async def fast_chat_response_generator(func_type: str = "chat", return_mode: str = "chat"):
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)
        try:
            active_mode = (return_mode or func_type or mode or "chat")
            shared_ctx = _get_shared_context(active_mode, history_limit=FAST_CHAT_HISTORY_LIMIT)
            execution_guard_prompt = (
                "You are an enterprise office assistant. Execute tasks directly when intent is clear.\n"
                "1) If the user asks for direct drafting, produce output immediately without repeated clarification.\n"
                "2) For short follow-up prompts, continue the task based on recent context.\n"
                "3) If information is incomplete, make minimal assumptions and list them at the end."
            )
            system_prompt = _merge_system_prompt(execution_guard_prompt, personalization_system_prompt)
            history_text = shared_ctx.get("history_text", "")
            base_prompt = ""
            if _should_force_direct_draft(message, history_text):
                base_prompt = (
                    "用户已明确允许自由发挥并要求直接开始。"
                    "请直接输出可用初稿，不要重复询问主题、字数或格式。"
                )
            prompt = _wrap_prompt_with_shared_context(
                base_prompt,
                shared_ctx,
                user_message=message,
            )

            async for chunk in ask_llm_stream_async(
                prompt,
                system_prompt=system_prompt,
                model_type=model_backend,
                stop_checker=_is_cancelled,
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
                    if _is_cancelled():
                        return
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            if _is_cancelled():
                return

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

            if _is_cancelled():
                return
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
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)

        try:
            shared_ctx = _get_shared_context("search", history_limit=4)
            history_text = shared_ctx.get("history_text", "")

            is_weather_intent = _is_weather_query(message)
            is_stock_intent = _is_stock_query(message)

            if is_weather_intent:
                city = _extract_city(message, history_text)
                search_query = f"{city} ??"
            elif is_stock_intent:
                search_query = _normalize_stock_query(message)
            else:
                search_query = message

            yield json.dumps({"t": "c", "v": f"> 正在搜索：{search_query}\n\n"}, ensure_ascii=False) + "\n"

            raw_results = perform_web_search(search_query)
            search_results = [r for r in raw_results if r.get("link") != "#"][:6]

            if _is_cancelled():
                return

            if not search_results:
                no_result_text = "未检索到可靠结果。请换个关键词再试。"
                full_reply_clean = no_result_text
                yield json.dumps({"t": "c", "v": no_result_text}, ensure_ascii=False) + "\n"
            else:
                context_lines = []
                for i, item in enumerate(search_results[:5], start=1):
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    link = str(item.get("link") or "").strip()
                    context_lines.append(f"[{i}] {title}\n{snippet}\n来源: {link}")

                search_context = "\n\n".join(context_lines)
                response_prompt = (
                    "请基于以下检索结果，给出准确、简洁、可执行的回答。"
                    "如果结果不足，请明确说明不确定性，不要编造。\n\n"
                    f"用户问题:\n{message}\n\n"
                    f"检索结果:\n{search_context}"
                )

                async for chunk in ask_llm_stream_async(
                    response_prompt,
                    model_type=model_backend,
                    stop_checker=_is_cancelled,
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
                        if _is_cancelled():
                            return
                        yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            if _is_cancelled():
                return

            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": message,
                        "func_type": "search",
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": full_reply_clean,
                        "func_type": "search",
                    }).execute()
                except Exception as e:
                    print(f"[Search] history save failed: {e}")

            if _is_cancelled():
                return
            yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"[Search Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"Search error: {e}"}, ensure_ascii=False) + "\n"
            if not _is_cancelled():
                yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"

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
            db_events = db_manager.query_fast(
                DEFAULT_DB_NAME,
                message,
                model_type=model_backend,
                response_instruction=personalization_system_prompt,
                history_context=shared_ctx.get("history_text", ""),
                summary_context=shared_ctx.get("summary_context", ""),
                session_state=shared_ctx.get("session_state", ""),
                active_context_content=shared_ctx.get("active_context", ""),
                stop_checker=_is_cancelled,
            )
            async for event in _iter_sync_stream(db_events):
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
                    if _is_cancelled():
                        return
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            if _is_cancelled():
                return

            # Persist conversation history
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
                    print(f"History save failed: {e}")

            if _is_cancelled():
                return
            yield json.dumps({"t": "m", "sid": session_id, "mode": "database", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [DB Mode Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\nDatabase mode failed: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "database", "end": True}, ensure_ascii=False) + "\n"

    # --------------------------------------------------------
    # ✅ 审计模式 (Audit Mode)：直连 Audit Service
    # --------------------------------------------------------
    async def audit_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if not run_audit_pipeline:
            yield json.dumps({"t": "c", "v": "Audit service is not available."}, ensure_ascii=False) + "\n"
            if _is_cancelled():
                return
            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"
            return

        full_reply = ""
        # Normalize message before passing to Audit Service
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
                if _is_cancelled():
                    return
                if chunk:
                    full_reply += chunk
                    out = push_chunk(chunk)
                    if out:
                        yield json.dumps({"t": "c", "v": out}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            out = flush_chunk()
            if out:
                for part in _split_text(out):
                    if _is_cancelled():
                        return
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            # Persist audit run for traceability
            if _is_cancelled():
                return
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

            if _is_cancelled():
                return
            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"❌ [Audit Mode Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\nAudit mode failed: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "audit", "end": True}, ensure_ascii=False) + "\n"


    # --------------------------------------------------------
    # Fallback to RAG + LLM when audit path is unavailable
    # --------------------------------------------------------
    async def rag_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if search_user_documents is None:
            yield json.dumps({"t": "c", "v": "RAG document search module is not loaded."}, ensure_ascii=False) + "\n"
            if not _is_cancelled():
                yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"
            return

        full_reply = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)

        try:
            shared_ctx = _get_shared_context("rag", history_limit=6)
            docs = search_user_documents(user_id, message, k=6, match_threshold=0.25)
            chunks, srcs = _to_text_and_sources(docs)

            if srcs:
                yield json.dumps({"t": "m", "sid": session_id, "src": srcs}, ensure_ascii=False) + "\n"

            if _is_cancelled():
                return

            active_context = (shared_ctx.get("active_context", "") or "").strip()[:RAG_MAX_ACTIVE_CONTEXT_CHARS]

            if not chunks and not active_context:
                no_doc = "未检索到可用文档内容，请先上传文档后再试。"
                full_reply = no_doc
                yield json.dumps({"t": "c", "v": no_doc}, ensure_ascii=False) + "\n"
            else:
                kb_sections = []
                if active_context:
                    kb_sections.append(f"[附件上下文]\n{active_context}")
                if chunks:
                    for i, c in enumerate(chunks[:RAG_MAX_CHUNKS], start=1):
                        trimmed = (c or "")[:RAG_MAX_CHUNK_CHARS]
                        kb_sections.append(f"[片段{i}]\n{trimmed}")

                kb_text = "\n\n".join(kb_sections)
                if len(kb_text) > RAG_MAX_KB_TEXT_CHARS:
                    kb_text = kb_text[:RAG_MAX_KB_TEXT_CHARS] + "\n\n[truncated]"

                prompt = (
                    "你是企业知识库助手。请仅基于给定资料回答，不能编造。"
                    "若资料不足，请明确指出并给出下一步建议。\n\n"
                    f"用户问题:\n{message}\n\n"
                    f"知识资料:\n{kb_text}"
                )
                prompt = _wrap_prompt_with_shared_context(
                    prompt,
                    shared_ctx,
                    user_message=message,
                )

                async for chunk in ask_llm_stream_async(
                    prompt,
                    model_type=model_backend,
                    stop_checker=_is_cancelled,
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
                        if _is_cancelled():
                            return
                        yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)

            if _is_cancelled():
                return

            if user_id != "anonymous":
                try:
                    sb = require_supabase()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "user",
                        "content": message,
                        "func_type": "rag",
                    }).execute()
                    sb.table("history").insert({
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": "assistant",
                        "content": full_reply,
                        "func_type": "rag",
                    }).execute()
                except Exception as e:
                    print(f"[RAG] history save failed: {e}")

            if _is_cancelled():
                return
            yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"[RAG Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"RAG error: {e}"}, ensure_ascii=False) + "\n"
            if not _is_cancelled():
                yield json.dumps({"t": "m", "sid": session_id, "mode": "rag", "end": True}, ensure_ascii=False) + "\n"

    async def langgraph_response_generator():
        # Unified fallback error handling
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        if not app_graph:
            err_msg = "LangGraph module is not loaded."
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
        history_msgs = _get_langchain_history(user_id, session_id, mode=mode, query=message)

        initial_state = {
            "hub": hub,
            "messages": history_msgs,
            "intent": "chat",
            "agent_output": {},
            "final_response": "",
            "explain_steps": [],
            "sources": [],  # 初始化为空
            # [New] carry mode / modelId into graph state
            "mode": mode,
            "modelId": req.modelId,
            # [New] carry model_backend into graph state
            "model_backend": model_backend
        }

        full_reply_display = ""
        full_reply_clean = ""  # full cleaned reply for storage
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
                query=message,
            )
            final_prompt = _build_cache_friendly_prompt(
                user_message=message,
                session_state=session_state_text,
                summary_context=final_prompt,
                recent_history=recent_history_for_layout,
            )

            # ✨ [新特性] 展示 Agent 思考过程 (Explainable AI)
            if explain_steps:
                steps_str = "\n".join([f"> {step}" for step in explain_steps])
                yield json.dumps({"t": "c", "v": f"{steps_str}\n\n"}, ensure_ascii=False) + "\n"
                # Include explain-steps in final streamed output
                full_reply_display += f"{steps_str}\n\n"

            # Continue with synthesizer streaming
            if sources:
                yield json.dumps({"t": "m", "sid": session_id, "src": sources}, ensure_ascii=False) + "\n"

            # === Layer 4 Output: 流式输出最终回答 ===
            print(f"💬 [Synthesizer] Streaming response for intent: {final_intent} using {model_backend}")

            # 使用用户选择的后端模型 (local / cloud)
            push_chunk, flush_chunk = _make_text_buffer()
            async for chunk in ask_llm_stream_async(
                final_prompt,
                system_prompt=personalization_system_prompt,
                model_type=model_backend,
                stop_checker=_is_cancelled,
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
                    if _is_cancelled():
                        return
                    yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0)

            if _is_cancelled():
                return

            # === Persist history (user + assistant) ===
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
                    print(f"History save failed: {e}")

            # Graph stage fallback handling
            if _is_cancelled():
                return
            yield json.dumps(
                {"t": "m", "sid": session_id, "mode": final_intent, "end": True},
                ensure_ascii=False
            ) + "\n"

        except Exception as e:
            print(f"❌ [Graph Error]: {e}")
            import traceback
            traceback.print_exc()
            yield json.dumps({"t": "c", "v": f"\nGraph execution failed: {str(e)}"}, ensure_ascii=False) + "\n"

    # Unified stream response exit
    is_report_write_mode = (model_id == "3") or _is_report_write_prompt(message)
    auto_routing_enabled = (mode == "general") and (not is_report_write_mode)
    is_doc_query = _is_doc_query(message) if auto_routing_enabled else False
    is_db_query = False
    if auto_routing_enabled and _is_db_question_by_tables:
        try:
            is_db_query = _is_db_question_by_tables(message)[0]
        except Exception:
            is_db_query = False

    if auto_routing_enabled and not is_db_query:
        is_db_query = _looks_like_db_request(message)

    if auto_routing_enabled and FAST_CHAT_DIRECT and not context_content and not is_doc_query and not is_db_query:
        return _stream(fast_chat_response_generator())

    # 🚀 Fast-path: auto-routed DB questions go straight to database mode (skip LangGraph + extra LLM)
    if auto_routing_enabled and is_db_query and not is_doc_query:
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
# Chat route entrypoint
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

