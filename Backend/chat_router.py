from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import os
import hashlib
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# 🔧 配置区域：请在这里填入你的 API Key
# -----------------------------------------------------------------------------
# 1. Bing Web Search API (推荐，国内极稳): https://www.microsoft.com/en-us/bing/apis/bing-web-search-api
BING_SUBSCRIPTION_KEY = os.environ.get("BING_SEARCH_V7_KEY", "") or os.environ.get("BING_API_KEY", "")
BING_SEARCH_ENDPOINT = os.environ.get("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search").strip()

# 2. SerpAPI (备选): https://serpapi.com/
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
# 3. Serper (Google Search API): https://serper.dev/
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
# 4. Tavily Search API: https://tavily.com/
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
SEARCH_PROVIDER_ORDER = [
    p.strip().lower()
    for p in os.getenv("SEARCH_PROVIDER_ORDER", "bing,serpapi,serper,tavily,scrape").split(",")
    if p.strip()
]
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "6000"))
OCR_SUMMARY_MAX_CONTEXT_CHARS = int(os.getenv("OCR_SUMMARY_MAX_CONTEXT_CHARS", "32000"))
RAG_MAX_ACTIVE_CONTEXT_CHARS = int(os.getenv("RAG_MAX_ACTIVE_CONTEXT_CHARS", "2600"))
RAG_MAX_CHUNK_CHARS = int(os.getenv("RAG_MAX_CHUNK_CHARS", "700"))
RAG_MAX_CHUNKS = int(os.getenv("RAG_MAX_CHUNKS", "6"))
RAG_MAX_KB_TEXT_CHARS = int(os.getenv("RAG_MAX_KB_TEXT_CHARS", "4200"))
FAST_CHAT_DIRECT = os.getenv("FAST_CHAT_DIRECT", "true").lower() != "false"
FAST_CHAT_HISTORY_LIMIT = int(os.getenv("FAST_CHAT_HISTORY_LIMIT", "14"))
PROMPT_USER_MAX_CHARS = int(os.getenv("PROMPT_USER_MAX_CHARS", "2600"))
PROMPT_SESSION_STATE_MAX_CHARS = int(os.getenv("PROMPT_SESSION_STATE_MAX_CHARS", "1800"))
PROMPT_SUMMARY_MAX_CHARS = int(os.getenv("PROMPT_SUMMARY_MAX_CHARS", "3200"))
PROMPT_HISTORY_MAX_CHARS = int(os.getenv("PROMPT_HISTORY_MAX_CHARS", "5200"))
CONTEXT_COMPACTION_SOURCE_MAX_CHARS = int(os.getenv("CONTEXT_COMPACTION_SOURCE_MAX_CHARS", "12000"))
PROMPT_LAYOUT_VERSION = "v1"
CONTEXT_EVENT_SCAN_LIMIT = int(os.getenv("CONTEXT_EVENT_SCAN_LIMIT", "60"))
CONTEXT_COMPACTION_SCAN_LIMIT = int(os.getenv("CONTEXT_COMPACTION_SCAN_LIMIT", "160"))
CONTEXT_COMPACTION_TRIGGER_CHARS = int(os.getenv("CONTEXT_COMPACTION_TRIGGER_CHARS", "2500"))
CONTEXT_COMPACTION_MIN_INTERVAL = int(os.getenv("CONTEXT_COMPACTION_MIN_INTERVAL", "4"))
HISTORY_TAIL_MIN_RECORDS = int(os.getenv("HISTORY_TAIL_MIN_RECORDS", "10"))
STREAM_UNTHROTTLED = os.getenv("STREAM_UNTHROTTLED", "true").lower() != "false"
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
memory_vector = None
try:
    from langgraph_agent import app_graph, _is_db_question_by_tables
    try:
        from langgraph_agent import memory_summary, memory_vector
    except Exception:
        memory_summary = None
        memory_vector = None
except ImportError as e:
    _is_db_question_by_tables = None
    memory_vector = None
    print(
        f"⚠️ [ChatRouter] 警告: 无法导入 langgraph_agent ({e})。请确保安装了 langgraph: `pip install langgraph langchain-core`")
except Exception as e:
    _is_db_question_by_tables = None
    memory_vector = None
    print(f"⚠️ [ChatRouter] langgraph_agent 加载失败: {e}")

router = APIRouter(prefix="/api", tags=["Chat"])
_ACTIVE_STREAM_CANCELS: Dict[str, threading.Event] = {}
_ACTIVE_STREAM_LOCK = threading.Lock()


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    user_id: Optional[str] = None
    session_id: Optional[str] = None

    # 前端字段：mode / modelId
    mode: Optional[str] = Field(default="general", description="对话模式：general / database / rag / search / audit ...")
    modelId: Optional[str] = Field(default=None, description="Selected model ID from frontend")

    # 新字段：模型后端选择
    model_backend: Optional[str] = Field(default="local", description="backend: local (Qwen) / cloud (DeepSeek)")

    # 上下文内容（OCR/会议/订单文本）
    context_content: Optional[str] = None
    # 显式文件列表（保留）
    files: List[str] = []
    personalization: Dict[str, Any] = Field(default_factory=dict)


class RenameRequest(BaseModel):
    title: str


# ------------------------------------------------------------
# 助手：清理历史内容
# ------------------------------------------------------------
def _sanitize_history_content(text: str) -> str:
    """Clean history text and remove tool/debug traces before prompting."""
    if text is None:
        return ""
    s = str(text)

    # 删除可能泄漏到历史记录中的特殊令牌
    s = s.replace("<|im_start|>", "").replace("<|im_end|>", "")
    # 移除前端/中间层注入的 meta 行
    s = re.sub(r'^\s*Assistant:\s*\{.*?\}\s*$', '', s, flags=re.MULTILINE)
    # 移除工具/调试日志，保留正常对话内容。
    noisy_line_patterns = [
        r'^\s*>\s*(THOUGHT|ACTION|OBSERVATION|TOOL|SEARCH|WEATHER|STOCK|RETRY)\b.*$',
        r'^\s*(Thought|Action|Observation)\s*:.*$',
        r'^\s*工具调用\s*:.*$',
    ]
    for pattern in noisy_line_patterns:
        s = re.sub(pattern, '', s, flags=re.MULTILINE | re.IGNORECASE)

    # 移除 ReAct 过程日志
    s = re.sub(r'^\s*ReAct\s*(思考|行动|观察).*$', '', s, flags=re.MULTILINE)
    # 删除通用调试横幅行
    s = re.sub(r'^\s*\[[A-Z_]+\].*$', '', s, flags=re.MULTILINE)
    # 折叠过多的空白行
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
        "风险与待事项",
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
        active_context_content: str = "",
        recent_history: str = "",
) -> str:
    safe_user_message = _truncate_context(user_message, max_len=PROMPT_USER_MAX_CHARS)
    safe_session_state = _truncate_context(session_state, max_len=PROMPT_SESSION_STATE_MAX_CHARS)
    safe_summary_context = _truncate_context(summary_context, max_len=PROMPT_SUMMARY_MAX_CHARS)
    safe_active_context = _truncate_context(
        active_context_content,
        max_len=max(RAG_MAX_ACTIVE_CONTEXT_CHARS, OCR_SUMMARY_MAX_CONTEXT_CHARS),
    )
    safe_recent_history = _truncate_context(recent_history, max_len=PROMPT_HISTORY_MAX_CHARS)

    def section(name: str, content: str, allow_empty: bool = False) -> str:
        body = (content or "").strip()
        if not body and not allow_empty:
            body = "(empty)"
        return f"[{name}]\n{body}"

    blocks = [
        section("PromptLayout", f"version={PROMPT_LAYOUT_VERSION}"),
        section("SessionState", safe_session_state),
        section("SummaryContext", safe_summary_context),
    ]
    if safe_active_context:
        blocks.append(section("ActiveContext", safe_active_context))
    blocks.extend([
        section("RecentHistory", safe_recent_history),
        section("User", safe_user_message),
        section("Assistant", "", allow_empty=True),
    ])
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

        # 对于长中文短语，请使用 n-gram，这样仍然可以检测到主题重叠。
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


def _normalize_weather_city_name(text: Optional[str], default: str = "") -> str:
    raw = str(text or "").strip()
    if not raw:
        return default

    city = urllib.parse.unquote(raw)
    city = re.sub(
        r"(今天|今日|明天|后天|昨天|昨日|今晚|今早|今晨|当前|现在|实时|最新|最近|这几天|这两天|本周|下周|周末|天天|当天)",
        " ",
        city,
    )
    city = re.sub(
        r"(天气|气温|温度|weather|forecast|怎么样|如何|怎样|情况|预报|查询|查下|查一下|看下|看看|请问|帮我|一下|呢|么|吗)",
        " ",
        city,
        flags=re.IGNORECASE,
    )
    city = re.sub(r"[的地得]", " ", city)
    city = re.sub(r"[，,。.!！?？;；:：/\\|]+", " ", city)
    city = re.sub(r"\s{2,}", " ", city).strip()
    if not city:
        return default

    zh_parts = re.findall(r"[\u4e00-\u9fa5]{2,12}", city)
    if zh_parts:
        municipalities = {"北京", "上海", "天津", "重庆", "香港", "澳门"}
        preferred = [
            p for p in zh_parts
            if p.endswith(("市", "区", "县", "州", "旗", "自治州", "特别行政区")) or p in municipalities
        ]
        picked = (preferred[0] if preferred else zh_parts[0]).strip()
        picked = re.sub(r"(今天|今日|明天|后天|昨天|昨日)$", "", picked).strip()
        if picked:
            return picked

    en_parts = re.findall(r"[A-Za-z][A-Za-z\\-]{1,30}", city)
    if en_parts:
        return en_parts[0]

    return city or default


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
    return bool(re.search(r"(这个|那个|继续|然后|按这个|照这个|就这|同上|上一条|上面)", q))


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
    keep_tail_count = max(HISTORY_TAIL_MIN_RECORDS, 8 if is_followup_turn else 6)

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


def _maybe_store_long_term_hint(user_id: str, text: str):
    if user_id == "anonymous" or not memory_vector:
        return
    clean = _sanitize_history_content(text)
    if not clean:
        return
    triggers = ["从现在起", "以后", "记住", "不要", "必须", "我的项目", "我想", "我叫"]
    if not any(k in clean for k in triggers):
        return
    importance = 5 if any(k in clean for k in ["从现在起", "以后", "必须", "不要", "记住"]) else 3
    try:
        memory_vector.store(user_id=user_id, text=clean, importance=importance)
    except Exception:
        pass


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
        f"Conversation:\n{source_text[:CONTEXT_COMPACTION_SOURCE_MAX_CHARS]}\n\n"
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


_ROUTE_DISABLE_NEGATIVE_WORDS = (
    "不要", "别", "别再", "不用", "不必", "禁止", "请勿", "勿", "不准", "拒绝",
)

_ROUTE_DISABLE_TARGET_PATTERNS = {
    "database": (
        "数据库", "查数据库", "查库", "sql", "db", "数据表", "查表", "查数据",
    ),
    "rag": (
        "rag", "文档", "文件", "知识库", "附件", "上传文件", "检索文档",
    ),
    "search": (
        "搜索", "联网", "上网", "网页检索", "websearch", "internet", "查网", "在线搜索",
    ),
    "audit": (
        "审计", "风险审查", "风险评估", "合规检查",
    ),
}


def _extract_disabled_routes(text: Optional[str]) -> set[str]:
    q = _normalize_match_text(text)
    if not q:
        return set()

    blocked: set[str] = set()
    neg = "|".join(_ROUTE_DISABLE_NEGATIVE_WORDS)

    for route, targets in _ROUTE_DISABLE_TARGET_PATTERNS.items():
        for target in targets:
            if re.search(fr"(?:{neg}).{{0,8}}(?:{target})", q) or re.search(fr"(?:{target}).{{0,4}}(?:{neg})", q):
                blocked.add(route)
                break

    return blocked


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
    if "database" in _extract_disabled_routes(text):
        return False

    q = _normalize_match_text(text)
    if not q:
        return False

    # 从白名单中直接命中表名。
    for table_name in ALLOWED_TABLES:
        if table_name.lower() in q:
            return True

    has_action = any(k in q for k in _DB_INTENT_ACTION_WORDS)
    has_entity = any(k in q for k in _DB_INTENT_ENTITY_WORDS)
    if has_action and has_entity:
        return True

    # 原始 SQL 模式
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


def _normalize_source_name(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = urllib.parse.unquote(text)
    text = text.replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text.strip()


def _build_doc_source(metadata: Dict[str, Any], content: Optional[str]) -> Dict[str, Any]:
    file_name = (
        _normalize_source_name(metadata.get("source"))
        or _normalize_source_name(metadata.get("file_name"))
        or _normalize_source_name(metadata.get("filename"))
        or _normalize_source_name(metadata.get("title"))
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

    # 优先使用实时片段内容，保证展示来源与实际证据一致。
    snippet = _make_snippet(content) if content else (metadata.get("snippet") or "")
    source = {
        "title": title,
        "file_name": file_name,
        "page": page_display,
        "snippet": snippet,
    }
    if metadata.get("source"):
        source["source"] = _normalize_source_name(metadata.get("source")) or file_name
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
        # 保存短期快照
        if isinstance(it, str):
            t = it.strip()
            if t:
                texts.append(t)
            continue

        # LangChain 文档
        page_content = getattr(it, "page_content", None)
        metadata = getattr(it, "metadata", None)

        if isinstance(page_content, str) and page_content.strip():
            texts.append(page_content.strip())

        # 构建紧凑的共享上下文
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


def _build_rag_chunk_entries(items, max_chunks: int = RAG_MAX_CHUNKS) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not items:
        return entries

    for it in items:
        if len(entries) >= max_chunks:
            break
        if it is None:
            continue

        if isinstance(it, str):
            text = it.strip()
            if not text:
                continue
            source = {
                "title": "检索片段",
                "file_name": "retrieved_text",
                "page": None,
                "snippet": _make_snippet(text),
                "type": "text",
            }
            entries.append({"text": text, "source": source})
            continue

        page_content = getattr(it, "page_content", None)
        metadata = getattr(it, "metadata", None)
        text = (page_content or "").strip() if isinstance(page_content, str) else ""
        if not text:
            continue
        source = _build_doc_source(metadata if isinstance(metadata, dict) else {}, text)
        entries.append({"text": text, "source": source})

    return entries


# ------------------------------------------------------------
# 搜索相关性评分助手
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

    # 1. 标题关键词加权
    for kw in query_keywords:
        kw = kw.lower()
        if kw in title:
            score += 3.0  # 标题包含关键词权重高
        if kw in snippet:
            score += 1.0  # 摘要包含关键词

    # 2. 域名可信度提升
    domain_boost = False
    for domain in HIGH_VALUE_DOMAINS:
        if domain in link:
            score += 5.0  # High-trust domain gets stronger weight
            domain_boost = True
            break

    # 3. 低价值域名惩罚
    if not domain_boost:
        for domain in LOW_VALUE_DOMAINS:
            if domain in link:
                score -= 2.0

    # 4. 非常短的片段惩罚
    if len(snippet) < 20:
        score -= 5.0

    return score


def _rank_search_results(results: List[dict], query: str, min_score: float = 3.0) -> List[dict]:
    """Rank and filter search results by relevance."""
    if not results:
        return []

    # 使用中英混合分词提取关键词；为空时再回退到空格分词。
    keywords = _extract_query_terms(query, max_terms=12)
    if not keywords:
        keywords = [k for k in query.split() if len(k) > 1]
    if not keywords and query.strip():
        keywords = [query.strip()]

    scored_results = []
    for r in results:
        score = _calculate_result_score(r, keywords)
        # 保持中间相关性分数
        r["_score"] = score
        if score >= min_score:
            scored_results.append(r)

    # 按分数降序排列
    scored_results.sort(key=lambda x: x["_score"], reverse=True)

    return scored_results


def _normalize_search_item(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    link = str(item.get("link") or "").strip()
    snippet = re.sub(r"\s+", " ", str(item.get("snippet") or "")).strip()
    if not link or link == "#" or link.startswith("javascript:") or link.startswith("/"):
        return None
    if not title:
        title = link
    normalized = {"title": title, "link": link, "snippet": snippet}
    # 保留可选元信息，供“实时性”增强提示和前端来源展示使用。
    for key in ("date", "source", "provider"):
        val = item.get(key)
        if val is not None and str(val).strip():
            normalized[key] = str(val).strip()
    return normalized


def _canonicalize_link(link: str) -> str:
    try:
        parsed = urllib.parse.urlparse(link or "")
        host = (parsed.netloc or "").lower().strip()
        path = (parsed.path or "").rstrip("/")
        if host:
            return f"{host}{path}"
    except Exception:
        pass
    return (link or "").strip().lower()


def _post_process_search_results(results: List[dict], query: str, max_results: int = 8) -> List[dict]:
    normalized: List[dict] = []
    seen = set()
    for item in results or []:
        row = _normalize_search_item(item)
        if not row:
            continue
        key = _canonicalize_link(row.get("link", ""))
        if key in seen:
            continue
        seen.add(key)
        normalized.append(row)

    if not normalized:
        return []

    # 先做一轮“核心词命中”过滤，减少主题偏移。
    core_terms = [t for t in _extract_query_terms(query, max_terms=8) if len(str(t)) >= 2][:4]
    if core_terms:
        strict_hits = []
        for row in normalized:
            hay = _normalize_match_text(
                f"{row.get('title', '')} {row.get('snippet', '')} {row.get('link', '')}"
            )
            if any(_normalize_match_text(t) in hay for t in core_terms):
                strict_hits.append(row)
        # 严格命中太少时不强制，避免把结果清空。
        if len(strict_hits) >= 2:
            normalized = strict_hits

    ranked = _rank_search_results(normalized, query, min_score=1.0)
    if ranked:
        if len(ranked) >= max_results:
            return ranked[:max_results]
        # 分数命中过少时，用原始结果补齐，避免上下文过窄导致答偏。
        ranked_keys = {_canonicalize_link(x.get("link", "")) for x in ranked}
        merged = list(ranked)
        for row in normalized:
            key = _canonicalize_link(row.get("link", ""))
            if key in ranked_keys:
                continue
            merged.append(row)
            if len(merged) >= max_results:
                break
        return merged[:max_results]
    return normalized[:max_results]


def _search_with_bing_api(query: str, max_results: int) -> List[dict]:
    if not BING_SUBSCRIPTION_KEY:
        return []
    import requests

    headers = {"Ocp-Apim-Subscription-Key": BING_SUBSCRIPTION_KEY}
    params = {"q": query, "count": max_results, "mkt": "zh-CN"}
    resp = requests.get(BING_SEARCH_ENDPOINT, headers=headers, params=params, timeout=8)
    if resp.status_code != 200:
        print(f"⚠️ [Bing API] Error {resp.status_code}: {resp.text[:240]}")
        return []
    data = resp.json()
    web_pages = data.get("webPages", {}).get("value", [])
    return [
        {
            "title": page.get("name"),
            "link": page.get("url"),
            "snippet": page.get("snippet", ""),
        }
        for page in web_pages
    ]


def _search_with_serpapi(query: str, max_results: int) -> List[dict]:
    if not SERPAPI_API_KEY:
        return []
    import requests

    params = {
        "engine": "bing",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "cc": "CN",
        "num": max_results,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ [SerpAPI] Error {resp.status_code}: {resp.text[:240]}")
        return []
    data = resp.json()
    organic = data.get("organic_results", [])
    return [
        {
            "title": res.get("title"),
            "link": res.get("link"),
            "snippet": res.get("snippet", ""),
        }
        for res in organic[:max_results]
    ]


def _search_with_serper(query: str, max_results: int, prefer_fresh: bool = False) -> List[dict]:
    if not SERPER_API_KEY:
        return []
    import requests

    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    if prefer_fresh:
        # 时效性优先：先走 news 接口，带最近一天过滤。
        news_payload = {"q": query, "num": max_results, "hl": "zh-cn", "gl": "cn", "tbs": "qdr:d"}
        news_resp = requests.post("https://google.serper.dev/news", headers=headers, json=news_payload, timeout=10)
        if news_resp.status_code == 200:
            news_data = news_resp.json()
            rows = news_data.get("news", [])
            if rows:
                return [
                    {
                        "title": row.get("title"),
                        "link": row.get("link"),
                        "snippet": row.get("snippet", ""),
                        "date": row.get("date", ""),
                        "source": row.get("source", ""),
                        "provider": "serper-news",
                    }
                    for row in rows[:max_results]
                ]
        else:
            print(f"⚠️ [Serper News] Error {news_resp.status_code}: {news_resp.text[:240]}")

    payload = {"q": query, "num": max_results, "hl": "zh-cn", "gl": "cn"}
    if prefer_fresh:
        payload["tbs"] = "qdr:d"
    resp = requests.post("https://google.serper.dev/search", headers=headers, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ [Serper] Error {resp.status_code}: {resp.text[:240]}")
        return []
    data = resp.json()
    organic = data.get("organic", [])
    return [
        {
            "title": res.get("title"),
            "link": res.get("link"),
            "snippet": res.get("snippet", ""),
            "provider": "serper-search",
        }
        for res in organic[:max_results]
    ]


def _search_with_tavily(query: str, max_results: int) -> List[dict]:
    if not TAVILY_API_KEY:
        return []
    import requests

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
    }
    resp = requests.post("https://api.tavily.com/search", json=payload, timeout=12)
    if resp.status_code != 200:
        print(f"⚠️ [Tavily] Error {resp.status_code}: {resp.text[:240]}")
        return []
    data = resp.json()
    rows = data.get("results", [])
    return [
        {
            "title": row.get("title"),
            "link": row.get("url"),
            "snippet": row.get("content", ""),
        }
        for row in rows[:max_results]
    ]


# ------------------------------------------------------------
# 天气工具API
# ------------------------------------------------------------
def tool_get_weather(city_name: str) -> List[dict]:
    """Get realtime weather from Moji only."""
    import requests
    import json as _json
    from bs4 import BeautifulSoup

    results: List[dict] = []
    print(f"☁️ [Weather Tool/Moji] Getting weather for: {city_name}")

    try:
        raw_city = str(city_name or "").strip()
        if not raw_city:
            raw_city = "北京"

        normalized_city = _normalize_weather_city_name(raw_city, default="北京")

        headers = {"User-Agent": "Mozilla/5.0"}
        city_search_url = f"https://tianqi.moji.com/api/citysearch/{urllib.parse.quote(normalized_city)}"
        city_resp = requests.get(city_search_url, headers=headers, timeout=8)
        if city_resp.status_code != 200:
            return results

        data = _json.loads(city_resp.text or "{}")
        city_rows = data.get("city_list", []) or []
        if not city_rows:
            return results

        def _is_poi_row(row: Dict[str, Any]) -> bool:
            labels = row.get("city_lable") or []
            for lb in labels:
                if isinstance(lb, dict) and "景点" in str(lb.get("name") or ""):
                    return True
            return False

        def _is_city_like_name(name: str) -> bool:
            n = str(name or "").strip()
            if not n:
                return False
            return any(n.endswith(suffix) for suffix in ("市", "区", "县", "州", "旗", "自治州", "特别行政区"))

        preferred_rows = [
            row for row in city_rows
            if isinstance(row, dict)
            and not _is_poi_row(row)
            and _is_city_like_name(row.get("localName") or row.get("name"))
        ]
        candidate_rows = preferred_rows if preferred_rows else [r for r in city_rows if isinstance(r, dict)]

        query_terms = _extract_query_terms(normalized_city, max_terms=8)
        query_norm = _normalize_match_text(normalized_city)

        def _score_city(row: Dict[str, Any], index: int) -> int:
            name = str(row.get("localName") or row.get("name") or "").strip()
            pname = str(row.get("localPname") or row.get("pname") or "").strip()
            full = f"{pname}{name}"
            full_norm = _normalize_match_text(full)
            score = max(0, 40 - index)
            if name in {normalized_city, f"{normalized_city}市", f"{normalized_city}区", f"{normalized_city}县"}:
                score += 160
            if query_norm and query_norm in full_norm:
                score += 90
            if query_norm and full_norm in query_norm:
                score += 50
            for term in query_terms:
                t_norm = _normalize_match_text(term)
                if t_norm and t_norm in full_norm:
                    score += 12
            if _is_poi_row(row):
                score -= 60
            return score

        best = max(
            enumerate(candidate_rows[:40]),
            key=lambda x: _score_city(x[1] if isinstance(x[1], dict) else {}, x[0]),
        )[1]

        local_name = str(best.get("localName") or best.get("name") or normalized_city).strip()
        city_id = str(best.get("cityId") or "").strip()
        if not city_id:
            return results

        redirect_url = f"https://tianqi.moji.com/api/redirect/{city_id}"
        page_resp = requests.get(redirect_url, headers=headers, timeout=10, allow_redirects=True)
        if page_resp.status_code != 200:
            return results
        moji_url = str(page_resp.url or redirect_url)

        soup = BeautifulSoup(page_resp.text, "html.parser")
        temp_node = soup.select_one(".wea_weather em")
        condition_node = soup.select_one(".wea_weather b")
        update_node = soup.select_one(".info_uptime")
        humidity_node = None
        for span in soup.select(".wea_about span"):
            txt = span.get_text(" ", strip=True)
            if "湿度" in txt:
                humidity_node = txt
                break
        aqi_node = soup.select_one(".wea_alert em")

        temp_text = temp_node.get_text(" ", strip=True) if temp_node else ""
        condition_text = condition_node.get_text(" ", strip=True) if condition_node else ""
        update_text = update_node.get_text(" ", strip=True) if update_node else ""
        aqi_text = aqi_node.get_text(" ", strip=True) if aqi_node else ""

        if not (temp_text or condition_text):
            return results

        snippet_parts: List[str] = []
        if temp_text:
            snippet_parts.append(f"温度: {temp_text}°C")
        if condition_text:
            snippet_parts.append(f"天气: {condition_text}")
        if humidity_node:
            snippet_parts.append(humidity_node)
        if aqi_text:
            snippet_parts.append(f"AQI: {aqi_text}")
        if update_text:
            snippet_parts.append(update_text)

        results.append({
            "type": "web",
            "title": f"{local_name} 实时天气",
            "link": moji_url,
            "snippet": " | ".join(snippet_parts),
            "source": "墨迹天气",
            "date": update_text.replace("更新", "").strip(),
            "provider": "moji",
        })
    except Exception as e:
        print(f"⚠️ [Weather Tool/Moji] Failed: {e}")

    return results


def tool_get_stock(query: str) -> List[dict]:
    """Get stock quote information."""
    import requests
    results = []
    print(f"📈 [Stock Tool] Analyzing query: {query}")
    try:
        headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
        raw_query = str(query or "").strip()
        cleaned_query = re.sub(
            r"(现在|当前|今日|最新|实时|公司|股价|股票|行情|价格|是多少|多少|呢|请问|想知道|查一下|看一下|一下|一下子)",
            " ",
            raw_query,
        )
        cleaned_query = re.sub(r"[，,。.!！?？;；:：]", " ", cleaned_query)
        cleaned_query = re.sub(r"\s{2,}", " ", cleaned_query).strip()
        if not cleaned_query:
            cleaned_query = raw_query

        direct_code = ""
        direct_name = cleaned_query
        direct_market = ""

        code_match = re.search(r"\b(?:sh|sz|hk)?\d{5,6}\b", raw_query.lower())
        us_match = re.search(r"\b[A-Za-z]{1,6}\b", raw_query)
        if code_match:
            direct_code = code_match.group(0).lower()
            if direct_code.isdigit():
                if len(direct_code) == 6:
                    direct_code = ("sh" if direct_code.startswith("6") else "sz") + direct_code
                elif len(direct_code) == 5:
                    direct_code = "hk" + direct_code
        elif us_match and len(raw_query.strip()) <= 16:
            token = us_match.group(0).lower()
            if token not in {"price", "stock", "quote", "today", "now"}:
                direct_code = f"gb_{token}"
                direct_name = us_match.group(0).upper()
                direct_market = "41"

        def _normalize_stock_code(raw_code: str, market_hint: str = "") -> str:
            code = str(raw_code or "").strip().lower()
            if not code:
                return ""
            if code.startswith(("sh", "sz", "hk", "gb_", "hf_", "nf_")):
                return code
            if code.startswith("us") and len(code) > 2:
                return f"gb_{code[2:]}"
            if code.isdigit():
                if len(code) == 6:
                    return ("sh" if code.startswith("6") else "sz") + code
                if len(code) == 5:
                    return "hk" + code
            if re.fullmatch(r"[a-z]{1,6}", code):
                if market_hint in {"41", "103"}:
                    return f"gb_{code}"
                return code
            return code

        candidates: List[Dict[str, Any]] = []
        if direct_code:
            candidates.append({"code": _normalize_stock_code(direct_code, direct_market), "name": direct_name, "score": 999})

        query_candidates = [cleaned_query]
        if cleaned_query != raw_query:
            query_candidates.append(raw_query)

        for q in query_candidates:
            suggest_url = (
                "https://suggest3.sinajs.cn/suggest/type=&key="
                f"{urllib.parse.quote(q)}&name=suggestdata_{int(uuid4().int % 10000)}"
            )
            resp = requests.get(suggest_url, headers=headers, timeout=6)
            if resp.status_code != 200:
                continue
            match = re.search(r'="(.*?)"', resp.text)
            payload = match.group(1) if match else ""
            if not payload:
                continue
            entries = [e for e in payload.split(";") if e.strip()]
            query_terms = _extract_query_terms(cleaned_query, max_terms=8)
            query_norm = _normalize_match_text(cleaned_query)

            for idx, entry in enumerate(entries[:40]):
                cols = entry.split(",")
                if len(cols) < 4:
                    continue
                market = str(cols[1] if len(cols) > 1 else "").strip()
                raw_code = str(cols[3] if len(cols) > 3 else cols[2]).strip()
                primary_name = str(cols[0] if len(cols) > 0 else "").strip()
                display_name = str(cols[4] if len(cols) > 4 else primary_name).strip() or primary_name
                code = _normalize_stock_code(raw_code, market)
                if not code:
                    continue

                hay = _normalize_match_text(f"{primary_name} {display_name} {code}")
                score = max(0, 50 - idx)
                if query_norm and query_norm in hay:
                    score += 90
                for t in query_terms:
                    tn = _normalize_match_text(t)
                    if tn and tn in hay:
                        score += 10
                if "指数" in (primary_name + display_name) and "指数" not in cleaned_query:
                    score -= 45
                if "etf" in (primary_name + display_name).lower() and "etf" not in cleaned_query.lower():
                    score -= 20
                if market in {"11", "12", "31", "41", "71", "73", "103"}:
                    score += 6

                candidates.append({
                    "code": code,
                    "name": display_name or primary_name or code,
                    "score": score,
                })

        if not candidates:
            return results

        best = max(candidates, key=lambda x: float(x.get("score", 0)))
        stock_code = str(best.get("code") or "").strip()
        stock_name = str(best.get("name") or stock_code).strip()
        if not stock_code:
            return results

        query_codes = [stock_code]
        if stock_code.startswith("hk"):
            query_codes.append(f"rt_{stock_code}")

        content = ""
        for c in query_codes:
            hq_url = f"http://hq.sinajs.cn/list={c}"
            hq_resp = requests.get(hq_url, headers=headers, timeout=6)
            if hq_resp.status_code != 200:
                continue
            val_match = re.search(r'="(.*?)"', hq_resp.text)
            if val_match and val_match.group(1).strip():
                content = val_match.group(1).strip()
                stock_code = c
                break

        if not content:
            return results

        vals = content.split(",")
        source_link = "https://finance.sina.com.cn/"
        source_date = ""
        snippet = ""

        if stock_code.startswith(("sh", "sz")) and len(vals) > 31:
            open_p = vals[1]
            prev_close = vals[2]
            price = vals[3]
            high = vals[4]
            low = vals[5]
            date = vals[30]
            tm = vals[31]
            source_date = f"{date} {tm}".strip()
            try:
                change = float(price) - float(prev_close)
                percent = (change / float(prev_close)) * 100 if float(prev_close) else 0.0
                snippet = (
                    f"最新价: {price} | 涨跌: {change:.3f} ({percent:.2f}%) | "
                    f"今开: {open_p} | 高/低: {high}/{low} | 时间: {source_date}"
                )
            except Exception:
                snippet = f"最新价: {price} | 今开: {open_p} | 高/低: {high}/{low} | 时间: {source_date}"
            source_link = f"https://finance.sina.com.cn/realstock/company/{stock_code}/nc.shtml"
        elif stock_code.startswith("rt_hk") and len(vals) > 18:
            name_cn = vals[1] or stock_name
            open_p = vals[2]
            prev_close = vals[3]
            high = vals[4]
            low = vals[5]
            price = vals[6]
            change = vals[7]
            pct = vals[8]
            date = vals[17] if len(vals) > 17 else ""
            tm = vals[18] if len(vals) > 18 else ""
            source_date = f"{date} {tm}".strip()
            snippet = (
                f"最新价: {price} HKD | 涨跌: {change} ({pct}%) | "
                f"今开: {open_p} | 高/低: {high}/{low} | 时间: {source_date}"
            )
            stock_name = name_cn
            source_link = f"https://stock.finance.sina.com.cn/hkstock/quotes/{stock_code.replace('rt_hk', '')}.html"
        elif stock_code.startswith("hk") and len(vals) > 17:
            name_cn = vals[1] or stock_name
            open_p = vals[2]
            prev_close = vals[3]
            high = vals[4]
            low = vals[5]
            price = vals[6]
            change = vals[7]
            pct = vals[8]
            date = vals[17] if len(vals) > 17 else ""
            tm = vals[18] if len(vals) > 18 else ""
            source_date = f"{date} {tm}".strip()
            snippet = (
                f"最新价: {price} HKD | 涨跌: {change} ({pct}%) | "
                f"今开: {open_p} | 高/低: {high}/{low} | 时间: {source_date}"
            )
            stock_name = name_cn
            source_link = f"https://stock.finance.sina.com.cn/hkstock/quotes/{stock_code.replace('hk', '')}.html"
        elif stock_code.startswith("gb_") and len(vals) > 7:
            name_cn = vals[0] or stock_name
            price = vals[1] if len(vals) > 1 else ""
            pct = vals[2] if len(vals) > 2 else ""
            dt = vals[3] if len(vals) > 3 else ""
            change = vals[4] if len(vals) > 4 else ""
            high = vals[5] if len(vals) > 5 else ""
            low = vals[6] if len(vals) > 6 else ""
            source_date = dt
            snippet = (
                f"最新价: {price} USD | 涨跌: {change} ({pct}%) | "
                f"高/低: {high}/{low} | 时间: {source_date}"
            )
            stock_name = name_cn
            source_link = f"https://finance.sina.com.cn/stock/usstock/c/{stock_code}.html"
        else:
            # 兜底格式
            price = vals[1] if len(vals) > 1 else (vals[0] if vals else "N/A")
            snippet = f"最新价: {price}"

        results.append({
            "type": "web",
            "title": f"{stock_name} 实时报价",
            "link": source_link,
            "snippet": snippet,
            "source": "新浪财经",
            "date": source_date,
            "provider": "sina-stock",
        })

    except Exception as e:
        print(f"⚠️ [Stock Tool] Failed: {e}")

    return results


def tool_get_gold_price(query: str = "") -> List[dict]:
    """
    Get realtime gold quote from Sina futures interface.
    Returns direct quote snippets with source timestamp.
    """
    import requests

    results: List[dict] = []
    print(f"🥇 [Gold Tool] Query: {query}")
    try:
        headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
        # 伦敦金（现货）+ 纽约黄金（期货）双源，提高稳定性。
        codes = ["hf_XAU", "hf_GC"]
        for code in codes:
            resp = requests.get(f"https://hq.sinajs.cn/list={code}", headers=headers, timeout=6)
            if resp.status_code != 200:
                continue
            match = re.search(r'="(.*?)"', resp.text)
            if not match or not match.group(1):
                continue
            vals = match.group(1).split(",")
            if len(vals) < 14:
                continue
            latest = (vals[0] or "").strip()
            previous = (vals[1] or "").strip()
            high = (vals[4] or "").strip() if len(vals) > 4 else ""
            low = (vals[5] or "").strip() if len(vals) > 5 else ""
            quote_time = (vals[6] or "").strip() if len(vals) > 6 else ""
            quote_date = (vals[12] or "").strip() if len(vals) > 12 else ""
            name = (vals[13] or code).strip() if len(vals) > 13 else code
            if not latest:
                continue
            snippet_parts = [f"最新报价: {latest}"]
            if previous:
                snippet_parts.append(f"前收: {previous}")
            if high and low:
                snippet_parts.append(f"高/低: {high}/{low}")
            if quote_date or quote_time:
                snippet_parts.append(f"时间: {quote_date} {quote_time}".strip())
            results.append({
                "type": "web",
                "title": f"{name} 实时报价",
                "link": f"https://finance.sina.com.cn/futures/quotes/{code}.shtml",
                "snippet": " | ".join(snippet_parts),
                "date": f"{quote_date} {quote_time}".strip(),
                "source": "新浪财经",
                "provider": "sina-gold",
            })
    except Exception as e:
        print(f"⚠️ [Gold Tool] Failed: {e}")

    return results


# ------------------------------------------------------------
# 搜索工具：首选官方API，回退到抓取
# ------------------------------------------------------------
def perform_web_search(query: str, max_results: int = 8) -> List[dict]:
    """
    Smart web search routing:
    1. Intent tools (weather/stock) when applicable
    2. Serper API only
    """
    # 先清理“写作指令/字数约束”噪声，提升检索命中。
    raw_query = str(query or "")
    query = re.sub(r"(至少|不少于|不低于|最多|不超过|不多于|不高于)?\s*\d{2,5}\s*字", " ", raw_query)
    query = re.sub(r"(请|帮我|麻烦)?(介绍一下|介绍|总结一下|总结|写一篇|写一段|分析一下|分析)", " ", query)
    query = re.sub(r"[，,。.!！?？;；:：]+", " ", query)
    query = re.sub(r"\s{2,}", " ", query).strip() or raw_query

    # --- 1. 首先尝试直接工具（天气/股票）---
    q_lower = query.lower()
    if "天气" in q_lower or "weather" in q_lower or "气温" in q_lower:
        city = _normalize_weather_city_name(query, default="北京")
        weather_res = tool_get_weather(city)
        # 用户要求天气仅用墨迹来源：无论是否命中，都不回退其他天气来源。
        return weather_res

    if any(k in q_lower for k in ["股价", "股票", "行情", "stock", "price"]):
        stock_res = tool_get_stock(query)
        if stock_res:
            return stock_res

    if any(k in q_lower for k in ["金价", "黄金", "现货金", "伦敦金", "comex gold", "gold"]):
        gold_res = tool_get_gold_price(query)
        if gold_res:
            return gold_res

    print(f"🔍 [Search] Trying provider=serper query={query}")
    try:
        freshness_keywords = ["现在", "当前", "实时", "最新", "today", "now", "今日", "刚刚", "近况"]
        prefer_fresh = any(k in q_lower for k in freshness_keywords)
        effective_query = query
        if prefer_fresh:
            now_stamp = datetime.now().strftime("%Y-%m-%d")
            effective_query = f"{query} {now_stamp} 最新"

        provider_rows = _search_with_serper(effective_query, max_results=max_results * 2, prefer_fresh=prefer_fresh)
        picked = _post_process_search_results(provider_rows, query, max_results=max_results)
        if picked:
            print(f"✅ [Search] provider=serper results={len(picked)}")
            return picked
    except Exception as e:
        print(f"⚠️ [Search] provider=serper failed: {e}")

    print("⚠️ [Search] Serper returned no usable results.")
    return []


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
# 修复了创作者/模特问题的身份回复。
IDENTITY_FIXED_REPLY = "我是由浅夏安然创造的imagine agent，是你的办公小助手，感谢使用。"

_IDENTITY_CN_PATTERNS = [
    r"你是谁",
    r"你是.*(创造|开发|构建|训练).*的",
    r"(谁|谁在).*?(创造|开发|构建|训练).*你",
    r"你是(哪家|哪个|什么)(公司|厂商|团队)(的)?",
    r"你(归属|隶属|来自|出自).*(公司|厂商|团队)",
    r"你(用的|是什么|属于)?什么模型",
    r"你是(哪家|哪家的|哪家公司|哪个厂商|哪一家的).*(模型|大模型|llm)",
    r"你(来自|出自).*(哪家|哪个公司|哪个厂商)",
    r"你的(来源|本家|背后).*(模型|大模型|llm|公司|厂商)",
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
    # 关键词兜底：来源归属类提问一律视为身份问题。
    if any(k in normalized for k in ("公司", "厂商", "团队")) and any(
        k in normalized for k in ("你是", "你来自", "你出自", "你归属", "你隶属")
    ):
        return True
    # 关键词兜底：任何同时包含“模型/llm + 来源归属”的提问都视为身份问题。
    if ("模型" in normalized or "llm" in normalized) and any(
        k in normalized for k in ("哪家", "来源", "本家", "厂商", "公司", "来自", "出自")
    ):
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
        if STREAM_UNTHROTTLED:
            def push(text: str) -> Optional[str]:
                if not text:
                    return None
                return text

            def flush() -> Optional[str]:
                return None

            return push, flush

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
        if STREAM_UNTHROTTLED:
            return [text]
        if len(text) <= size:
            return [text]
        return [text[i:i + size] for i in range(0, len(text), size)]

    # 1. 请求验证
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

    # 模型后端选择（local / cloud）
    model_backend = req.model_backend or "local"
    model_id = (req.modelId or "").strip()

    mode = _normalize_mode(req.mode)
    # 硬防护：选择会议模式时，强制会议模式以避免意外的 RAG 路由。
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

    blocked_routes = _extract_disabled_routes(message)
    if blocked_routes:
        print(f"🛑 [Router] User disabled routes: {sorted(blocked_routes)}")
        if mode in blocked_routes and mode in {"database", "rag", "search", "audit"}:
            mode = "general"
            print("🛑 [Router] Requested mode is blocked by user text, fallback -> general")

    context_limit = OCR_SUMMARY_MAX_CONTEXT_CHARS if mode == "ocr_summary" else MAX_CONTEXT_CHARS
    context_content = _truncate_context(req.context_content, max_len=context_limit)
    if mode == "ocr_summary":
        print(f"[OCR Summary] session={session_id} context_chars={len(context_content or '')}")
    requested_source_files = [
        str(name).strip()
        for name in (req.files or [])
        if isinstance(name, str) and str(name).strip()
    ]
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
    _maybe_store_long_term_hint(user_id, message)

    print(
        f"🚀 [Chat] New Request: User={user_id}, Session={session_id}, Mode={mode}, Backend={model_backend}, Files={len(requested_source_files)}"
    )

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

        compaction_payload: Optional[Dict[str, Any]] = None
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
            compaction_payload = None
            session_state = ""

        summary_context = ""
        try:
            hub = ContextHub(
                user_id=user_id,
                session_id=session_id,
                query=message,
                active_context_content=active_context,
                ui_mode=normalized_mode
            )

            # 将压缩的中期状态注入结构化集线器内存中。
            if isinstance(compaction_payload, dict):
                facts = _normalize_text_list(compaction_payload.get("facts"), max_items=10, max_len=180)
                preferences = _normalize_text_list(compaction_payload.get("preferences"), max_items=8, max_len=140)
                constraints = _normalize_text_list(compaction_payload.get("constraints"), max_items=8, max_len=180)
                open_items = _normalize_text_list(compaction_payload.get("open_items"), max_items=8, max_len=180)
                if preferences or constraints:
                    hub.add_memory_tokens(preferences + constraints, source="会话压缩")
                if facts or open_items:
                    hub.add_compressed_facts(facts + open_items, source="会话压缩")

            # 尽可能在快速路径中提取长期记忆片段。
            if memory_vector and not active_context and normalized_mode in {"general", "chat", "rag", "database"}:
                try:
                    docs = memory_vector.retrieve(user_id, message, top_k=4) or []
                    long_mem_snippets: List[str] = []
                    for d in docs:
                        snippet = _sanitize_history_content(getattr(d, "page_content", "") or "")
                        if not snippet:
                            continue
                        snippet = _truncate_context(snippet, max_len=420)
                        if snippet in long_mem_snippets:
                            continue
                        long_mem_snippets.append(snippet)
                        if len(long_mem_snippets) >= 4:
                            break
                    if long_mem_snippets:
                        hub.add_long_term_memory(long_mem_snippets, source="长期记忆检索")
                except Exception:
                    pass

            if memory_summary:
                history_msgs = _get_langchain_history(
                    user_id,
                    session_id,
                    limit=max(8, history_limit),
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
                hub.history_summary = history_text[:1200]

            summary_context = hub.get_combined_context(max_len=3600)
            if (
                summary_context
                and normalized_mode != "ocr_summary"
                and not _is_context_related(message, summary_context, min_hits=1)
            ):
                # 当主题转移时，删除陈旧的摘要上下文。
                summary_context = ""
        except Exception:
            summary_context = ""

        active_context_limit = OCR_SUMMARY_MAX_CONTEXT_CHARS if normalized_mode == "ocr_summary" else RAG_MAX_ACTIVE_CONTEXT_CHARS
        bundle = {
            "history_text": _truncate_context(history_text or "", max_len=max(PROMPT_HISTORY_MAX_CHARS, 1600)),
            "summary_context": _truncate_context(summary_context or "", max_len=max(PROMPT_SUMMARY_MAX_CHARS, 1800)),
            "session_state": _truncate_context(session_state or "", max_len=max(PROMPT_SESSION_STATE_MAX_CHARS, 1200)),
            "active_context": _truncate_context(active_context or "", max_len=active_context_limit),
        }
        shared_context_cache[cache_key] = bundle
        return bundle

    async def _get_shared_context_async(
            target_mode: Optional[str] = None,
            history_limit: int = FAST_CHAT_HISTORY_LIMIT,
    ) -> Dict[str, str]:
        return await asyncio.to_thread(_get_shared_context, target_mode, history_limit)

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
            active_context_content=shared_ctx.get("active_context", ""),
            recent_history=(recent_history if recent_history is not None else shared_ctx.get("history_text", "")),
        )

    # --------------------------------------------------------
    # 快速回退路径：无图表的聊天模式
    # --------------------------------------------------------
    async def fast_chat_response_generator(func_type: str = "chat", return_mode: str = "chat"):
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)
        try:
            active_mode = (return_mode or func_type or mode or "chat")
            shared_ctx = await _get_shared_context_async(active_mode, history_limit=FAST_CHAT_HISTORY_LIMIT)
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
        if any(k in t for k in ["股票", "股价", "行情", "stock", "ticker", "涨跌"]):
            return True
        if "price" in t and re.search(r"\b(?:sh|sz|hk|us)?\d{5,6}\b|\b[a-z]{1,5}\b", t):
            return True
        return False

    def _is_gold_query(text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ["金价", "黄金", "伦敦金", "现货金", "comex gold", "gold"])

    def _is_realtime_sensitive_query(text: str) -> bool:
        t = (text or "").lower()
        freshness_words = ["现在", "当前", "实时", "最新", "today", "now", "今日", "刚刚", "最新价格", "现价"]
        domain_words = ["天气", "气温", "温度", "股票", "股价", "行情", "黄金", "金价", "汇率", "油价", "指数"]
        return any(k in t for k in freshness_words) and any(k in t for k in domain_words)

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
        for cand in candidates:
            normalized = _normalize_weather_city_name(cand)
            if normalized:
                return normalized
        fallback = _normalize_weather_city_name(text, default="北京")
        return fallback or "北京"

    def _normalize_stock_query(text: str) -> str:
        if not text:
            return ""
        q = text.replace("股票", "").replace("股价", "").replace("行情", "").replace("价格", "").strip()
        return q or text

    def _extract_length_requirement(text: str) -> Optional[Dict[str, int]]:
        src = str(text or "")
        if not src:
            return None

        # 至少/不低于 N 字
        m_min = re.search(r"(至少|不少于|不低于)\s*(\d{2,5})\s*字", src)
        if m_min:
            return {"kind": 1, "value": int(m_min.group(2))}

        # 最多/不超过 N 字
        m_max = re.search(r"(最多|不超过|不多于|不高于)\s*(\d{2,5})\s*字", src)
        if m_max:
            return {"kind": 2, "value": int(m_max.group(2))}

        # N字（默认视为目标字数）
        m_exact = re.search(r"(\d{2,5})\s*字", src)
        if m_exact:
            return {"kind": 3, "value": int(m_exact.group(1))}

        return None

    def _count_visible_chars(text: str) -> int:
        # 近似“字数”：去掉空白后计数，兼容中英文混排。
        return len(re.sub(r"\s+", "", str(text or "")))

    def _is_length_requirement_satisfied(text: str, req: Optional[Dict[str, int]]) -> bool:
        if not req:
            return True
        n = _count_visible_chars(text)
        val = int(req.get("value", 0))
        kind = int(req.get("kind", 0))
        if kind == 1:  # min
            return n >= val
        if kind == 2:  # max
            return n <= val
        if kind == 3:  # exact-ish
            tolerance = max(30, int(val * 0.12))
            return (val - tolerance) <= n <= (val + tolerance)
        return True

    def _build_length_rule_text(req: Optional[Dict[str, int]]) -> str:
        if not req:
            return ""
        val = int(req.get("value", 0))
        kind = int(req.get("kind", 0))
        if kind == 1:
            return f"必须不少于{val}字。"
        if kind == 2:
            return f"必须不超过{val}字。"
        if kind == 3:
            return f"目标字数约{val}字（允许±12%）。"
        return ""

    def _sanitize_search_query(text: str) -> str:
        q = str(text or "")
        if not q:
            return q
        # 移除常见生成约束（字数、语气类）避免污染检索词。
        q = re.sub(r"(至少|不少于|不低于|最多|不超过|不多于|不高于)?\s*\d{2,5}\s*字", " ", q)
        q = re.sub(r"(请|帮我|麻烦)?(介绍一下|介绍|总结一下|总结|写一篇|写一段|分析一下|分析)", " ", q)
        q = re.sub(r"[，,。.!！?？;；:：]+", " ", q)
        q = re.sub(r"\s{2,}", " ", q).strip()
        return q or str(text or "")

    def _extract_recent_user_queries(history_text: str, limit: int = 6) -> List[str]:
        rows: List[str] = []
        for line in str(history_text or "").splitlines():
            raw = line.strip()
            if not raw.lower().startswith("user:"):
                continue
            content = _sanitize_history_content(raw[5:].strip())
            if content:
                rows.append(content)
        if len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def _detect_query_domain(text: str) -> str:
        if _is_weather_query(text):
            return "weather"
        if _is_stock_query(text):
            return "stock"
        if _is_gold_query(text):
            return "gold"
        return ""

    def _is_explicit_followup_query(text: str) -> bool:
        if _looks_like_followup_turn(text):
            return True
        t = _normalize_match_text(text)
        if not t:
            return False
        if re.search(r"(呢|那呢|然后呢|继续|接着|再说|再讲|再来点|同上|上一条|上面)$", t):
            return True
        return t in {"今天呢", "现在呢", "然后", "继续", "还有呢", "那这个呢"}

    def _build_contextual_search_query(user_text: str, history_text: str) -> str:
        current = _sanitize_search_query(user_text)
        if not current:
            return str(user_text or "").strip()

        current_norm = _normalize_match_text(current)
        current_domain = _detect_query_domain(current)
        explicit_followup = _is_explicit_followup_query(current)
        short_ambiguous = (
            len(current_norm) <= 8
            and any(k in current_norm for k in ["呢", "如何", "怎么样", "多少", "几个", "多大", "几点"])
            and not current_domain
        )
        needs_context = explicit_followup or short_ambiguous
        if not needs_context:
            return current

        recent_users = _extract_recent_user_queries(history_text, limit=8)
        anchor = ""
        for candidate in reversed(recent_users):
            if _normalize_match_text(candidate) == _normalize_match_text(current):
                continue
            if _looks_like_followup_turn(candidate):
                continue
            anchor = _sanitize_search_query(candidate)
            if anchor:
                break

        if not anchor:
            return current

        anchor_domain = _detect_query_domain(anchor)
        if current_domain and anchor_domain and current_domain != anchor_domain:
            return current

        if current_domain and not explicit_followup:
            return current

        merged_query = f"{anchor} {current}"
        merged_query = re.sub(r"\s{2,}", " ", merged_query).strip()
        # 仅在追问场景拼接，且保留长度上限，避免污染跨主题检索。
        return merged_query[:160] if merged_query else current
    async def search_response_generator():
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply_clean = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)

        try:
            shared_ctx = await _get_shared_context_async("search", history_limit=FAST_CHAT_HISTORY_LIMIT)
            history_text = shared_ctx.get("history_text", "")
            now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            contextual_user_query = _build_contextual_search_query(message, history_text)

            intent_probe = f"{message} {contextual_user_query}".strip()
            message_domain = _detect_query_domain(message)
            probe_domain = _detect_query_domain(intent_probe)
            intent_domain = message_domain or probe_domain

            is_weather_intent = intent_domain == "weather"
            is_stock_intent = intent_domain == "stock"
            is_gold_intent = intent_domain == "gold"
            is_realtime_query = _is_realtime_sensitive_query(message) or (
                _is_explicit_followup_query(message) and _is_realtime_sensitive_query(intent_probe)
            )
            length_req = _extract_length_requirement(message)

            if is_weather_intent:
                city_probe = message if message_domain == "weather" else intent_probe
                city = _extract_city(city_probe, history_text)
                search_query = f"{city} 天气"
            elif is_stock_intent:
                search_query = contextual_user_query or message
            elif is_gold_intent:
                search_query = "黄金 实时价格"
            else:
                search_query = contextual_user_query or message

            search_query = _sanitize_search_query(search_query)

            yield json.dumps({"t": "c", "v": f"> 正在搜索：{search_query}\n\n"}, ensure_ascii=False) + "\n"

            raw_results = await asyncio.to_thread(perform_web_search, search_query)
            search_results = _post_process_search_results(raw_results, search_query, max_results=6)

            if _is_cancelled():
                return

            if not search_results:
                no_result_text = "未检索到可靠结果。请换个关键词再试。"
                full_reply_clean = no_result_text
                yield json.dumps({"t": "c", "v": no_result_text}, ensure_ascii=False) + "\n"
            else:
                skip_llm_generation = False
                search_sources = []
                for item in search_results[:5]:
                    source_date = str(item.get("date") or "").strip()
                    source_name = str(item.get("source") or "").strip()
                    search_sources.append({
                        "type": "web",
                        "title": str(item.get("title") or "").strip(),
                        "link": str(item.get("link") or "").strip(),
                        "snippet": str(item.get("snippet") or "").strip(),
                        "date": source_date,
                        "source": source_name,
                    })
                if search_sources:
                    yield json.dumps({"t": "m", "sid": session_id, "src": search_sources}, ensure_ascii=False) + "\n"

                # 对“实时数值型短问”直接返回工具结果，避免 LLM 二次改写数值。
                needs_analysis = any(k in (message or "") for k in ["分析", "原因", "预测", "趋势", "影响", "解读", "建议", "展望"])
                if (is_weather_intent or is_stock_intent or is_gold_intent) and not needs_analysis:
                    lines = ["以下为实时检索结果："]
                    for i, item in enumerate(search_results[:3], start=1):
                        title = str(item.get("title") or "").strip()
                        snippet = str(item.get("snippet") or "").strip()
                        source_name = str(item.get("source") or "").strip()
                        source_date = str(item.get("date") or "").strip()
                        link = str(item.get("link") or "").strip()
                        meta = " | ".join([m for m in [source_name, source_date] if m])
                        lines.append(f"{i}. {title}")
                        if snippet:
                            lines.append(f"   {snippet}")
                        if meta:
                            lines.append(f"   {meta}")
                        if link:
                            lines.append(f"   来源: {link}")
                    full_reply_clean = "\n".join(lines).strip()
                    for part in _split_text(full_reply_clean):
                        if _is_cancelled():
                            return
                        yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                        await asyncio.sleep(0)
                    if _is_cancelled():
                        return
                    skip_llm_generation = True

                if not skip_llm_generation:
                    context_lines = []
                    for i, item in enumerate(search_results[:5], start=1):
                        title = str(item.get("title") or "").strip()
                        snippet = str(item.get("snippet") or "").strip()
                        link = str(item.get("link") or "").strip()
                        source_date = str(item.get("date") or "").strip()
                        source_name = str(item.get("source") or "").strip()
                        extra_tags = []
                        if source_name:
                            extra_tags.append(f"来源机构: {source_name}")
                        if source_date:
                            extra_tags.append(f"发布时间: {source_date}")
                        extra_line = ("\n" + " | ".join(extra_tags)) if extra_tags else ""
                        context_lines.append(f"[{i}] {title}\n{snippet}\n来源: {link}{extra_line}")

                    search_context = "\n\n".join(context_lines)
                    length_rule_text = _build_length_rule_text(length_req)
                    response_prompt = (
                        "你是企业联网检索助手。"
                        "只能基于下方“检索结果”回答，不要使用未提供的事实。\n"
                        "回答规则：\n"
                        "1) 先给结论，再给2-5条关键依据；\n"
                        "2) 每条关键事实后标注来源编号，如[1][3]；\n"
                        "3) 若证据不足或互相冲突，明确写“信息不足/信息冲突”；\n"
                        "4) 不要编造来源，不要输出与问题无关内容；\n"
                        "5) 必须完整满足用户原问题里的硬性要求（字数、格式、语气、输出结构）。\n"
                        f"当前本地时间: {now_local}\n"
                        f"字数要求: {length_rule_text or '未指定'}\n"
                        f"时效性要求: {'高（优先最新信息）' if is_realtime_query else '普通'}\n\n"
                        f"用户问题:\n{message}\n\n"
                        f"检索结果:\n{search_context}\n\n"
                        "请使用中文回答。"
                    )
                    if personalization_system_prompt:
                        response_prompt = f"{personalization_system_prompt}\n\n{response_prompt}"
                    # 若用户明确给出字数约束，改为“先整段生成 -> 校验 -> 必要时重写”，减少忽略约束的概率。
                    if length_req:
                        draft = await asyncio.to_thread(ask_llm, response_prompt, model_backend)
                        final_answer = draft
                        if not _is_length_requirement_satisfied(draft, length_req):
                            revise_prompt = (
                                "你上一版回答没有满足字数要求。请严格按要求重写，不要丢失关键信息。\n"
                                f"字数要求: {length_rule_text}\n"
                                "要求：保留引用编号格式 [1][2]，不要编造新来源。\n\n"
                                f"用户问题:\n{message}\n\n"
                                f"检索结果:\n{search_context}\n\n"
                                f"上一版回答:\n{draft}\n\n"
                                "请直接输出重写后的最终答案。"
                            )
                            final_answer = await asyncio.to_thread(ask_llm, revise_prompt, model_backend)

                        full_reply_clean = str(final_answer or "")
                        for part in _split_text(full_reply_clean):
                            if _is_cancelled():
                                return
                            yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                            await asyncio.sleep(0)
                    else:
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
            shared_ctx = await _get_shared_context_async("database", history_limit=FAST_CHAT_HISTORY_LIMIT)
            # 来源：先发数据库信息，后续收到​​​​​​ SQL 事件后会追加
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

            # 保留对话历史记录
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
        # 在传递到审核服务之前对消息进行标准化
        # 这里直接传 raw message 即可
        try:
            shared_ctx = await _get_shared_context_async("audit", history_limit=FAST_CHAT_HISTORY_LIMIT)
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

            # 持续审计运行以实现可追溯性
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
    # 当审核路径不可用时回退到 RAG + LLM
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
            shared_ctx = await _get_shared_context_async("rag", history_limit=FAST_CHAT_HISTORY_LIMIT)
            # 当用户显式附加源文件时，将 RAG 与过时的聊天历史记录隔离。
            explicit_source_mode = bool(requested_source_files)
            if explicit_source_mode:
                shared_ctx = dict(shared_ctx or {})
                shared_ctx["history_text"] = ""
                shared_ctx["summary_context"] = ""
                shared_ctx["session_state"] = ""

            docs = await asyncio.to_thread(
                lambda: search_user_documents(
                    user_id=user_id,
                    query=message,
                    k=6,
                    match_threshold=0.25,
                    source_files=requested_source_files,
                )
            )
            rag_entries = _build_rag_chunk_entries(docs, max_chunks=RAG_MAX_CHUNKS)
            source_count = len(rag_entries)
            srcs: List[Dict[str, Any]] = [dict(e.get("source") or {}) for e in rag_entries if isinstance(e.get("source"), dict)]

            if srcs:
                yield json.dumps({"t": "m", "sid": session_id, "src": srcs}, ensure_ascii=False) + "\n"

            if _is_cancelled():
                return

            active_context = (shared_ctx.get("active_context", "") or "").strip()[:RAG_MAX_ACTIVE_CONTEXT_CHARS]

            if source_count == 0 and not active_context:
                no_doc = "未检索到可用文档内容，请先上传文档后再试。"
                full_reply = no_doc
                yield json.dumps({"t": "c", "v": no_doc}, ensure_ascii=False) + "\n"
            else:
                kb_sections = []
                if active_context and source_count == 0:
                    kb_sections.append(f"[附件上下文]\n{active_context}")
                if rag_entries:
                    for entry in rag_entries:
                        src_title = (entry.get("source") or {}).get("title") or "文档片段"
                        chunk_text = (entry.get("text") or "")[:RAG_MAX_CHUNK_CHARS]
                        kb_sections.append(f"[片段] {src_title}\n{chunk_text}")

                kb_text = "\n\n".join(kb_sections)
                if len(kb_text) > RAG_MAX_KB_TEXT_CHARS:
                    kb_text = kb_text[:RAG_MAX_KB_TEXT_CHARS] + "\n\n[truncated]"

                prompt = (
                    "你是企业知识库助手。请仅基于给定资料回答，不能编造。"
                    "若资料不足，请明确说明资料不足并给出下一步建议。\n\n"
                    f"用户问题:\n{message}\n\n"
                    f"知识片段:\n{kb_text}"
                )
                if explicit_source_mode:
                    prompt = (
                        "用户本轮已明确指定附件来源。"
                        "请仅依据本轮附件命中的知识片段回答，忽略历史会话中的其他文档内容。\n\n"
                        + prompt
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
        # 统一回退错误处理
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
        history_msgs = await asyncio.to_thread(
            lambda: _get_langchain_history(user_id, session_id, mode=mode, query=message)
        )

        initial_state = {
            "hub": hub,
            "messages": history_msgs,
            "intent": "chat",
            "agent_output": {},
            "final_response": "",
            "explain_steps": [],
            "sources": [],  # 初始化为空
            # [新增]将mode / modelId带入图状态
            "mode": mode,
            "modelId": req.modelId,
            # [新增]将model_backend带入图状态
            "model_backend": model_backend,
            # 用户显式禁用的功能路由（例如“不要查数据库”）。
            "disabled_routes": sorted(blocked_routes),
        }

        full_reply_display = ""
        full_reply_clean = ""  # full cleaned reply for storage
        final_intent = "general"

        try:
            # === 运行 LangGraph (Layer 1 -> Layer 4) ===
            print("⚙️ [Graph] Invoking 4-Layer Architecture...")

            # 同步调用 Graph，等待 Synthesizer 准备好最终 Prompt
            final_state = await asyncio.to_thread(app_graph.invoke, initial_state)

            final_prompt = final_state.get("final_response", message)
            final_intent = final_state.get("intent", "general")
            explain_steps = final_state.get("explain_steps", [])
            sources = final_state.get("sources", [])
            shared_ctx = await _get_shared_context_async(
                mode,
                history_limit=FAST_CHAT_HISTORY_LIMIT,
            )
            final_prompt = _wrap_prompt_with_shared_context(
                final_prompt,
                shared_ctx,
                user_message=message,
            )

            # ✨ [新特性] 展示 Agent 思考过程 (Explainable AI)
            if explain_steps:
                steps_str = "\n".join([f"> {step}" for step in explain_steps])
                yield json.dumps({"t": "c", "v": f"{steps_str}\n\n"}, ensure_ascii=False) + "\n"
                # 在最终流输出中包含解释步骤
                full_reply_display += f"{steps_str}\n\n"

            # 继续合成器流
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

            # === 保留历史记录（用户+助手）===
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
                        # “元数据”：{“来源”：来源}
                    }).execute()
                except Exception as e:
                    print(f"History save failed: {e}")

            # 图阶段回退处理
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

    # 统一流响应退出
    is_report_write_mode = (model_id == "3") or _is_report_write_prompt(message)
    auto_routing_enabled = (mode == "general") and (not is_report_write_mode)
    db_route_blocked = "database" in blocked_routes
    rag_route_blocked = "rag" in blocked_routes
    search_route_blocked = "search" in blocked_routes
    audit_route_blocked = "audit" in blocked_routes

    is_doc_query = _is_doc_query(message) if (auto_routing_enabled and not rag_route_blocked) else False
    is_db_query = False
    if auto_routing_enabled and (not db_route_blocked) and _is_db_question_by_tables:
        try:
            is_db_query = _is_db_question_by_tables(message)[0]
        except Exception:
            is_db_query = False

    if auto_routing_enabled and (not db_route_blocked) and not is_db_query:
        is_db_query = _looks_like_db_request(message)

    if auto_routing_enabled and FAST_CHAT_DIRECT and not context_content and not is_doc_query and not is_db_query:
        return _stream(fast_chat_response_generator())

    # 用户显式禁用某能力时，优先走通用回复，避免进入被禁用能力的自动路由。
    if auto_routing_enabled and blocked_routes and not is_doc_query and not is_db_query:
        return _stream(fast_chat_response_generator())

    # 🚀 快速路径：自动路由的数据库问题直接进入数据库模式（跳过 LangGraph + 额外的 LLM）
    if auto_routing_enabled and is_db_query and not is_doc_query:
        return _stream(database_response_generator())

    if mode == "database" and not db_route_blocked:
        return _stream(database_response_generator())
    if mode == "rag" and not rag_route_blocked:
        return _stream(rag_response_generator())
    if mode == "search" and not search_route_blocked:
        return _stream(search_response_generator())
    if mode == "audit" and not audit_route_blocked: # ✅ 新增 Audit 路由
        return _stream(audit_response_generator())

    if auto_routing_enabled:
        return _stream(langgraph_response_generator())

    return _stream(
        fast_chat_response_generator(func_type=mode, return_mode=mode),
        media_type="application/x-ndjson"
    )


# ------------------------------------------------------------
# 聊天路由入口点
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

