from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
import urllib.parse
import os
import hashlib
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header, Query, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

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
SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://127.0.0.1:8888").strip().rstrip("/")
SEARXNG_TIMEOUT_SECONDS = max(5, int(os.getenv("SEARXNG_TIMEOUT_SECONDS", "12")))
SEARXNG_LANGUAGE = (os.getenv("SEARXNG_LANGUAGE", "") or "").strip()
SEARXNG_SAFESEARCH = max(0, min(2, int(os.getenv("SEARXNG_SAFESEARCH", "0"))))
SEARXNG_ENGINES = ",".join(
    [
        engine.strip()
        for engine in os.getenv("SEARXNG_ENGINES", "bing,bing news,wikipedia,sogou").split(",")
        if engine.strip()
    ]
)
SEARCH_SCRAPE_PAGE_LIMIT = max(1, int(os.getenv("SEARCH_SCRAPE_PAGE_LIMIT", "2")))
SEARCH_SCRAPE_PAGE_LIMIT_REALTIME = max(1, int(os.getenv("SEARCH_SCRAPE_PAGE_LIMIT_REALTIME", "1")))
SEARCH_CONTEXT_PAGE_MAX_CHARS = max(700, int(os.getenv("SEARCH_CONTEXT_PAGE_MAX_CHARS", "1400")))
EXCHANGE_RATE_TIMEOUT_SECONDS = max(3, int(os.getenv("EXCHANGE_RATE_TIMEOUT_SECONDS", "6")))
EXCHANGE_RATE_CACHE_TTL_SECONDS = max(30, int(os.getenv("EXCHANGE_RATE_CACHE_TTL_SECONDS", "300")))
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
FEEDBACK_CONTEXT_FETCH_LIMIT = max(6, int(os.getenv("FEEDBACK_CONTEXT_FETCH_LIMIT", "32")))
FEEDBACK_CONTEXT_MAX_EXAMPLES = max(1, int(os.getenv("FEEDBACK_CONTEXT_MAX_EXAMPLES", "4")))
FEEDBACK_CONTEXT_ENTRY_MAX_CHARS = max(80, int(os.getenv("FEEDBACK_CONTEXT_ENTRY_MAX_CHARS", "220")))
# -----------------------------------------------------------------------------

from supabase_client import require_supabase, engine
from history_manager import (
    add_history_turn_to_supabase,
    delete_session,
    get_history,
    get_history_limited,
    get_history_page,
    get_user_sessions,
    rename_session,
    set_session_pinned,
)
from deepseek_llm import ask_llm_stream_async, ask_llm
from admin_utils import require_active_user

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

extract_supported_urls = None
scrape_urls_for_chat = None
SCRAPLING_AVAILABLE = False
SCRAPLING_IMPORT_ERROR = None
try:
    from webpage_scraper import (
        SCRAPLING_AVAILABLE,
        SCRAPLING_IMPORT_ERROR,
        extract_supported_urls,
        scrape_urls_for_chat,
    )
    if SCRAPLING_AVAILABLE:
        print("[ChatRouter] Scrapling webpage scraper loaded")
    else:
        print(f"⚠️ [ChatRouter] Scrapling unavailable: {SCRAPLING_IMPORT_ERROR}")
except Exception as e:
    SCRAPLING_AVAILABLE = False
    SCRAPLING_IMPORT_ERROR = e
    extract_supported_urls = None
    scrape_urls_for_chat = None
    print(f"⚠️ [ChatRouter] webpage_scraper 加载失败: {e}")

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
_CONTEXT_COMPACTION_INFLIGHT: set[str] = set()
_CONTEXT_COMPACTION_LOCK = threading.Lock()


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


class SessionPinRequest(BaseModel):
    pinned: bool = False


class ChatFeedbackRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    history_id: Optional[int] = Field(default=None, description="助手消息的 history.id")
    message_key: Optional[str] = Field(default=None, description="前端稳定消息键")
    feedback_type: Optional[str] = Field(default=None, description="up / down；为空表示清除反馈")
    user_message: Optional[str] = Field(default=None, description="配套用户提问")
    assistant_message: Optional[str] = Field(default=None, description="助手回复文本")
    mode: Optional[str] = Field(default=None, description="当前模式")
    model_backend: Optional[str] = Field(default=None, description="local / cloud")
    model_id: Optional[str] = Field(default=None, description="前端模型 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------
# 反馈持久化与运行时学习
# ------------------------------------------------------------
_CHAT_FEEDBACK_SCHEMA_READY = False


def _ensure_chat_feedback_schema() -> None:
    global _CHAT_FEEDBACK_SCHEMA_READY
    if _CHAT_FEEDBACK_SCHEMA_READY:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS public.chat_feedback (
                        id BIGSERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        history_id BIGINT NULL,
                        message_key TEXT NOT NULL,
                        feedback_type TEXT NOT NULL,
                        feedback_score SMALLINT NOT NULL,
                        user_message TEXT NULL,
                        assistant_message TEXT NULL,
                        mode TEXT NULL,
                        model_backend TEXT NULL,
                        model_id TEXT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT chat_feedback_feedback_type_check
                            CHECK (feedback_type IN ('up', 'down'))
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_feedback_user_message_key
                    ON public.chat_feedback (user_id, message_key)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_feedback_user_session_created
                    ON public.chat_feedback (user_id, session_id, updated_at DESC)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_feedback_user_mode_created
                    ON public.chat_feedback (user_id, mode, updated_at DESC)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_feedback_history_id
                    ON public.chat_feedback (history_id)
                    """
                )
            )
        _CHAT_FEEDBACK_SCHEMA_READY = True
    except Exception as e:
        print(f"[Feedback] ensure schema failed: {e}")


def _normalize_feedback_type(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if raw in {"up", "like", "thumbs_up", "positive", "helpful"}:
        return "up"
    if raw in {"down", "dislike", "thumbs_down", "negative", "unhelpful"}:
        return "down"
    return None


def _build_feedback_message_key(
        history_id: Optional[int] = None,
        message_key: Optional[str] = None,
        session_id: Optional[str] = None,
        assistant_message: Optional[str] = None,
) -> str:
    if history_id not in (None, ""):
        try:
            return f"h:{int(history_id)}"
        except Exception:
            pass

    provided = str(message_key or "").strip()
    if provided:
        return provided[:160]

    seed = f"{session_id or ''}|{assistant_message or ''}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"fallback:{digest}"


def _truncate_feedback_text(value: Optional[str], max_len: int = 8000) -> str:
    return _truncate_context(_sanitize_history_content(value or ""), max_len=max_len)


def _resolve_feedback_history_context(
        user_id: str,
        session_id: str,
        history_id: Optional[int],
        assistant_message: Optional[str],
        user_message: Optional[str],
) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {
        "history_id": None,
        "session_id": str(session_id or "").strip(),
        "assistant_message": _truncate_feedback_text(assistant_message),
        "user_message": _truncate_feedback_text(user_message),
        "mode": "",
    }
    if not user_id or not resolved["session_id"]:
        return resolved

    _ensure_chat_feedback_schema()

    try:
        with engine.begin() as conn:
            assistant_row = None
            if history_id not in (None, ""):
                assistant_row = conn.execute(
                    text(
                        """
                        SELECT id, session_id, role, content, func_type
                        FROM public.history
                        WHERE id = :history_id
                          AND user_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {"history_id": int(history_id), "user_id": str(user_id)},
                ).mappings().first()
                if assistant_row and str(assistant_row.get("role") or "").strip().lower() != "assistant":
                    assistant_row = None

            if assistant_row is None and resolved["assistant_message"]:
                assistant_row = conn.execute(
                    text(
                        """
                        SELECT id, session_id, role, content, func_type
                        FROM public.history
                        WHERE user_id = :user_id
                          AND session_id = :session_id
                          AND role = 'assistant'
                          AND content = :assistant_message
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "session_id": resolved["session_id"],
                        "assistant_message": resolved["assistant_message"],
                    },
                ).mappings().first()

            if assistant_row:
                resolved["history_id"] = int(assistant_row.get("id"))
                resolved["session_id"] = str(assistant_row.get("session_id") or resolved["session_id"])
                resolved["assistant_message"] = _truncate_feedback_text(assistant_row.get("content"))
                resolved["mode"] = str(assistant_row.get("func_type") or "").strip().lower()

                previous_user = conn.execute(
                    text(
                        """
                        SELECT id, content
                        FROM public.history
                        WHERE user_id = :user_id
                          AND session_id = :session_id
                          AND role = 'user'
                          AND id < :assistant_history_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "session_id": resolved["session_id"],
                        "assistant_history_id": int(assistant_row.get("id")),
                    },
                ).mappings().first()
                if previous_user:
                    resolved["user_message"] = _truncate_feedback_text(previous_user.get("content"))
    except Exception as e:
        print(f"[Feedback] resolve history context failed: {e}")

    return resolved


def _save_chat_feedback(
        *,
        user_id: str,
        session_id: str,
        history_id: Optional[int],
        message_key: str,
        feedback_type: str,
        user_message: Optional[str],
        assistant_message: Optional[str],
        mode: Optional[str],
        model_backend: Optional[str],
        model_id: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ensure_chat_feedback_schema()
    feedback_score = 1 if feedback_type == "up" else -1
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO public.chat_feedback (
                    user_id,
                    session_id,
                    history_id,
                    message_key,
                    feedback_type,
                    feedback_score,
                    user_message,
                    assistant_message,
                    mode,
                    model_backend,
                    model_id,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :session_id,
                    :history_id,
                    :message_key,
                    :feedback_type,
                    :feedback_score,
                    :user_message,
                    :assistant_message,
                    :mode,
                    :model_backend,
                    :model_id,
                    CAST(:metadata_json AS jsonb),
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id, message_key) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    history_id = EXCLUDED.history_id,
                    feedback_type = EXCLUDED.feedback_type,
                    feedback_score = EXCLUDED.feedback_score,
                    user_message = EXCLUDED.user_message,
                    assistant_message = EXCLUDED.assistant_message,
                    mode = EXCLUDED.mode,
                    model_backend = EXCLUDED.model_backend,
                    model_id = EXCLUDED.model_id,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = NOW()
                RETURNING id, message_key, feedback_type, feedback_score, history_id, session_id, updated_at
                """
            ),
            {
                "user_id": str(user_id),
                "session_id": str(session_id),
                "history_id": int(history_id) if history_id not in (None, "") else None,
                "message_key": str(message_key),
                "feedback_type": feedback_type,
                "feedback_score": feedback_score,
                "user_message": _truncate_feedback_text(user_message),
                "assistant_message": _truncate_feedback_text(assistant_message),
                "mode": str(mode or "").strip().lower() or None,
                "model_backend": str(model_backend or "").strip().lower() or None,
                "model_id": str(model_id or "").strip() or None,
                "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
            },
        ).mappings().first()
    return dict(row or {})


def _clear_chat_feedback(user_id: str, message_key: str) -> bool:
    _ensure_chat_feedback_schema()
    try:
        with engine.begin() as conn:
            deleted = conn.execute(
                text(
                    """
                    DELETE FROM public.chat_feedback
                    WHERE user_id = :user_id
                      AND message_key = :message_key
                    """
                ),
                {"user_id": str(user_id), "message_key": str(message_key)},
            )
        return bool((deleted.rowcount or 0) > 0)
    except Exception as e:
        print(f"[Feedback] clear failed: {e}")
        return False


def _get_session_feedback_map(user_id: str, session_id: str) -> Dict[str, str]:
    _ensure_chat_feedback_schema()
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT message_key, history_id, feedback_type
                    FROM public.chat_feedback
                    WHERE user_id = :user_id
                      AND session_id = :session_id
                    ORDER BY updated_at DESC
                    """
                ),
                {"user_id": str(user_id), "session_id": str(session_id)},
            ).mappings().all()
        feedback_map: Dict[str, str] = {}
        for row in rows:
            feedback_type = _normalize_feedback_type(row.get("feedback_type"))
            if not feedback_type:
                continue
            history_id = row.get("history_id")
            if history_id not in (None, ""):
                feedback_map[f"h:{int(history_id)}"] = feedback_type
            message_key = str(row.get("message_key") or "").strip()
            if message_key:
                feedback_map[message_key] = feedback_type
        return feedback_map
    except Exception as e:
        print(f"[Feedback] get session map failed: {e}")
        return {}


def _score_feedback_context_row(
        row: Dict[str, Any],
        *,
        session_id: str,
        mode: str,
        query_terms: List[str],
) -> int:
    score = 0
    row_mode = str(row.get("mode") or "").strip().lower()
    row_session_id = str(row.get("session_id") or "").strip()
    if row_mode and row_mode == mode:
        score += 4
    if row_session_id and row_session_id == session_id:
        score += 3
    corpus = _normalize_match_text(
        f"{row.get('user_message') or ''}\n{row.get('assistant_message') or ''}"
    )
    for term in query_terms:
        if term and term in corpus:
            score += 2
    return score


def _build_feedback_learning_context(
        user_id: str,
        session_id: str,
        mode: str,
        query: Optional[str],
) -> str:
    if not user_id or user_id == "anonymous":
        return ""

    _ensure_chat_feedback_schema()
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT session_id, history_id, feedback_type, user_message, assistant_message, mode, updated_at
                    FROM public.chat_feedback
                    WHERE user_id = :user_id
                    ORDER BY updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"user_id": str(user_id), "limit": FEEDBACK_CONTEXT_FETCH_LIMIT},
            ).mappings().all()
    except Exception as e:
        print(f"[Feedback] load learning context failed: {e}")
        return ""

    if not rows:
        return ""

    normalized_mode = str(mode or "").strip().lower()
    query_terms = _extract_query_terms(query, max_terms=8)
    positives: List[Dict[str, Any]] = []
    negatives: List[Dict[str, Any]] = []

    scored_rows = []
    for raw_row in rows:
        row = dict(raw_row)
        row["score"] = _score_feedback_context_row(
            row,
            session_id=str(session_id or "").strip(),
            mode=normalized_mode,
            query_terms=query_terms,
        )
        scored_rows.append(row)

    scored_rows.sort(
        key=lambda item: (
            int(item.get("score") or 0),
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )

    for row in scored_rows:
        feedback_type = _normalize_feedback_type(row.get("feedback_type"))
        if not feedback_type:
            continue
        payload = {
            "user_message": _truncate_context(str(row.get("user_message") or "").strip(), max_len=FEEDBACK_CONTEXT_ENTRY_MAX_CHARS),
            "assistant_message": _truncate_context(str(row.get("assistant_message") or "").strip(), max_len=FEEDBACK_CONTEXT_ENTRY_MAX_CHARS),
            "mode": str(row.get("mode") or "").strip().lower(),
        }
        if not payload["assistant_message"]:
            continue
        if feedback_type == "up" and len(positives) < FEEDBACK_CONTEXT_MAX_EXAMPLES:
            positives.append(payload)
        elif feedback_type == "down" and len(negatives) < FEEDBACK_CONTEXT_MAX_EXAMPLES:
            negatives.append(payload)
        if len(positives) >= FEEDBACK_CONTEXT_MAX_EXAMPLES and len(negatives) >= FEEDBACK_CONTEXT_MAX_EXAMPLES:
            break

    if not positives and not negatives:
        return ""

    lines = [
        "【用户反馈学习】",
        "以下是该用户历史上明确点赞/点踩过的回答样例。",
        "请吸收这些偏好：延续被点赞回答的表达方式，避免重复被点踩回答的问题。",
        "不要逐字复述历史回答，只提炼风格、结构、详略和可靠性偏好。",
    ]

    if positives:
        lines.append("点赞样例：")
        for item in positives:
            parts = []
            if item["user_message"]:
                parts.append(f"问题：{item['user_message']}")
            parts.append(f"回答片段：{item['assistant_message']}")
            lines.append("- " + " | ".join(parts))

    if negatives:
        lines.append("点踩样例：")
        for item in negatives:
            parts = []
            if item["user_message"]:
                parts.append(f"问题：{item['user_message']}")
            parts.append(f"应避免的回答片段：{item['assistant_message']}")
            lines.append("- " + " | ".join(parts))

    return "\n".join(lines)

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
    "介绍", "简介", "讲讲", "说说", "什么是", "是什么",
    "what", "which", "about", "please", "thanks", "thank", "tell", "show", "give",
}

_PROFILE_INTENT_TOKENS = (
    "介绍一下",
    "介绍",
    "简介",
    "是什么",
    "做什么",
    "是干什么",
    "是做什么",
    "讲讲",
    "说说",
    "聊聊",
    "了解一下",
    "科普一下",
)

_PROFILE_NOISE_KEYWORDS = (
    "待遇",
    "工资",
    "薪资",
    "面试",
    "招聘",
    "应聘",
    "学历",
    "笔试",
    "工作体验",
    "值得去",
)

_GENERAL_SEARCH_PREFIX_PATTERNS = (
    r"^(就|那就|那|请问|请|帮我|帮忙|麻烦你|麻烦|劳驾|给我|告诉我|我想知道|我想了解|我想问|想问下|想了解一下|想请教一下)\s*",
    r"^(分析一下|分析|总结一下|总结|介绍一下|介绍|讲一下|讲讲|说一下|说说|聊聊|解释一下|解释|说明一下|说明|看看|看下|查一下|查下|搜一下|搜下)\s*",
)

_GENERAL_SEARCH_TRAILING_PATTERNS = (
    r"\s*(一下|一下子|吧|呢|呀|啊|哈|啦|呗|吗|么)$",
    r"\s*(谢谢|谢谢你|麻烦了)$",
)

_QUESTION_SPLIT_PATTERN = (
    r"(为什么|为何|怎么|怎样|如何|是否|能否|有无|有没有|是什么|什么是|什么|哪些|哪个|哪家|哪位|谁|哪里|哪儿|几时|什么时候|多少|几个|多大|多高|多远|多长)"
)

_GENERIC_TERM_PREFIXES = ("做", "讲", "说", "聊", "查", "搜", "看", "问", "谈", "评")
_SUBJECTIVE_QUERY_HINTS = ("评价", "体验", "感受", "觉得", "怎么看", "如何看待", "口碑", "值得", "建议", "推荐")
_FRESH_SEARCH_HINTS = ("最新", "最近", "当前", "实时", "今日", "今天", "刚刚", "动态", "进展", "新闻", "资讯", "近况")
_REASON_SEARCH_HINTS = ("原因", "为什么", "为何")
_SEARCH_INTENT_TOKENS = (
    "最新",
    "最近",
    "当前",
    "实时",
    "今日",
    "今天",
    "动态",
    "进展",
    "新闻",
    "资讯",
    "原因",
    "为什么",
    "为何",
    "分析",
    "总结",
    "介绍",
    "简介",
    "讲解",
    "讲讲",
    "说说",
    "说明",
    "教程",
    "方法",
    "怎么",
    "如何",
    "怎样",
    "区别",
    "对比",
    "背景",
)
_LOW_SIGNAL_RESULT_HOSTS = (
    "zhidao.baidu.com",
    "wenku.baidu.com",
    "jingyan.baidu.com",
    "baijiahao.baidu.com",
    "tieba.baidu.com",
    "sj.qq.com",
    "coze.cn",
    "code.coze.cn",
    "yuanbao.tencent.com",
    "ima.qq.com",
    "design006.com",
    "designnavs.com",
    "atkoo.com",
    "zmt.cn",
)
_LOW_SIGNAL_RESULT_PATTERNS = (
    r"(电脑版官方正版|最新免费下载|图片免费下载|素材网站|作品下载平台|资源下载|导航站|下载中心|技能商店)",
    r"(app下载|软件下载|官方下载|安装包|免费下载)",
)
_FRESH_LOW_VALUE_HOSTS = (
    "linux.do",
    "v2ex.com",
    "zhihu.com",
    "bilibili.com",
    "reddit.com",
)
_NEWSY_RESULT_PATTERNS = (
    r"(新闻|快讯|日报|发布|报告|观察|资讯|新华社|人民网|新华网|光明网|科技日报|IT之家|Readhub|界面新闻|36氪|新浪科技|机器之心|量子位)",
)


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    picked: List[str] = []
    seen = set()
    for value in values or []:
        candidate = re.sub(r"\s{2,}", " ", str(value or "")).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        picked.append(candidate)
    return picked


def _normalize_match_text(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _light_clean_search_query(text: Optional[str]) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    q = re.sub(r"(至少|不少于|不低于|最多|不超过|不多于|不高于)?\s*\d{2,5}\s*字", " ", raw)
    q = re.sub(r"[\"'`“”‘’]", " ", q)
    prev = None
    while q != prev:
        prev = q
        for pattern in _GENERAL_SEARCH_PREFIX_PATTERNS:
            q = re.sub(pattern, "", q)
    for pattern in _GENERAL_SEARCH_TRAILING_PATTERNS:
        q = re.sub(pattern, "", q)
    q = re.sub(r"[，,。.!！?？;；:：/\\|]+", " ", q)
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q or raw


def _choose_searxng_language(query: Optional[str]) -> str:
    if SEARXNG_LANGUAGE:
        return SEARXNG_LANGUAGE
    return ""


def _is_fresh_search_query(text: Optional[str]) -> bool:
    raw = str(text or "")
    return any(token in raw for token in _FRESH_SEARCH_HINTS)


def _is_reason_search_query(text: Optional[str]) -> bool:
    raw = str(text or "")
    return any(token in raw for token in _REASON_SEARCH_HINTS)


def _build_general_search_query(text: Optional[str]) -> str:
    cleaned = _light_clean_search_query(text)
    if not cleaned:
        return ""

    topic_terms = _extract_topic_terms(cleaned, max_terms=4)
    if topic_terms:
        if _is_fresh_search_query(cleaned):
            return " ".join(_dedupe_preserve_order(topic_terms + ["最新", "动态"]))
        if _is_reason_search_query(cleaned):
            enriched_topics = [term for term in topic_terms if term not in {"汽车", "车"}]
            if any(token in cleaned for token in ("汽车", "造车")):
                enriched_topics.append("造车")
            return " ".join(_dedupe_preserve_order(enriched_topics + ["原因"]))

    keyword_query = cleaned
    keyword_query = re.sub(r"(为什么|为何)", " 原因 ", keyword_query)
    keyword_query = re.sub(r"(如何|怎么|怎样)", " ", keyword_query)
    keyword_query = re.sub(_QUESTION_SPLIT_PATTERN, " ", keyword_query)
    keyword_query = re.sub(
        r"(最新|最近|当前|实时|官网|价格|原因|简介|背景|区别|对比|教程|方法|原理|趋势|进展|发布|评测|案例|分析)",
        r" \1 ",
        keyword_query,
    )
    keyword_query = re.sub(
        r"(?:(?<=\s)|^)(做|讲|说|聊|查|搜|看|问|谈|评)(?=[\u4e00-\u9fff]{2,})",
        " ",
        keyword_query,
    )
    keyword_query = re.sub(r"[，,。.!！?？;；:：/\\|]+", " ", keyword_query)
    keyword_query = re.sub(r"\s{2,}", " ", keyword_query).strip()
    if len(keyword_query.split()) >= 2:
        return keyword_query
    return cleaned


def _is_profile_query(text: Optional[str]) -> bool:
    normalized = _normalize_match_text(text)
    if not normalized:
        return False
    return any(token in normalized for token in _PROFILE_INTENT_TOKENS)


def _extract_profile_subject(text: Optional[str]) -> str:
    subject = str(text or "")
    if not subject:
        return ""

    subject = re.sub(
        r"(请|帮我|麻烦|就|那就|那|先|再|给我|简单|大概|详细|具体|顺便|先给我|先帮我)",
        " ",
        subject,
    )
    subject = re.sub(
        r"(介绍一下|介绍|简介|是什么|是做什么的|做什么的|是干什么的|讲讲|说说|聊聊|了解一下|科普一下|一下)",
        " ",
        subject,
    )
    subject = re.sub(r"(的)?(基本情况|情况|信息|背景|资料|概况|介绍|简介)$", " ", subject)
    subject = re.sub(r"[\"'`“”‘’（）()【】\\[\\]<>《》]", " ", subject)
    subject = re.sub(r"[，,。.!！?？;；:：/\\\\|]+", " ", subject)
    subject = re.sub(r"\s{2,}", " ", subject).strip()
    return subject


def _extract_query_terms(text: Optional[str], max_terms: int = 14) -> List[str]:
    raw = _light_clean_search_query(text).lower()
    raw = re.sub(_QUESTION_SPLIT_PATTERN, " ", raw)
    raw = re.sub(r"\b(why|how|what|which|when|where|who|can|could|would|should|please)\b", " ", raw)
    raw = re.sub(r"\s{2,}", " ", raw).strip()
    terms: List[str] = []

    for zh_seq in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
        seq = zh_seq.strip()
        seq = re.sub(r"^(就|那就|那|请|帮我|帮|麻烦|先|再|给我)", "", seq)
        seq = re.sub(r"(一下|一下子|吧|呢|呀|啊|吗|么)$", "", seq)
        if not seq:
            continue
        if seq not in _QUERY_TERM_STOPWORDS:
            terms.append(seq)
        for prefix in _GENERIC_TERM_PREFIXES:
            if seq.startswith(prefix) and len(seq) >= 3:
                candidate = seq[len(prefix):].strip()
                if candidate and candidate not in _QUERY_TERM_STOPWORDS:
                    terms.append(candidate)
        if len(seq) <= 4:
            if seq not in _QUERY_TERM_STOPWORDS:
                terms.append(seq)
            continue

        # 仅在较长短语上补充少量 n-gram，避免把普通问句切成大量噪声碎片。
        for n in (4, 3):
            for i in range(0, len(seq) - n + 1):
                t = seq[i:i + n]
                if t and t not in _QUERY_TERM_STOPWORDS:
                    terms.append(t)

    for t in re.findall(r"[a-z0-9_+-]{2,}", raw):
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


def _extract_topic_terms(text: Optional[str], max_terms: int = 6) -> List[str]:
    cleaned = _light_clean_search_query(text)
    if not cleaned:
        return []

    work = re.sub(r"(为什么|为何)", " 原因 ", cleaned)
    work = re.sub(_QUESTION_SPLIT_PATTERN, " ", work)
    for token in sorted(_SEARCH_INTENT_TOKENS, key=len, reverse=True):
        work = work.replace(token, " ")
    work = re.sub(
        r"(?:(?<=\s)|^)(做|讲|说|聊|查|搜|看|问|谈|评)(?=[\u4e00-\u9fff]{2,})",
        " ",
        work,
    )
    work = re.sub(r"[，,。.!！?？;；:：/\\|]+", " ", work)
    work = re.sub(r"\s{2,}", " ", work).strip().lower()

    topic_terms: List[str] = []
    seen = set()

    def add_term(value: str) -> None:
        candidate = str(value or "").strip()
        if not candidate:
            return
        candidate = re.sub(r"^(就|那就|那|请|帮我|帮|麻烦|先|再|给我)", "", candidate)
        candidate = re.sub(r"(一下|一下子|吧|呢|呀|啊|吗|么)$", "", candidate)
        if not candidate or candidate in _QUERY_TERM_STOPWORDS:
            return
        normalized = _normalize_match_text(candidate)
        if not normalized or normalized in seen or len(normalized) <= 1:
            return
        seen.add(normalized)
        topic_terms.append(candidate)

    for zh_seq in re.findall(r"[\u4e00-\u9fff]{2,20}", work):
        seq = zh_seq.strip()
        for prefix in _GENERIC_TERM_PREFIXES:
            if seq.startswith(prefix) and len(seq) >= 3:
                add_term(seq[len(prefix):].strip())
        add_term(seq)
        if len(topic_terms) >= max_terms:
            break

    if len(topic_terms) < max_terms:
        for token in re.findall(r"[a-z0-9_+-]{2,}", work):
            add_term(token)
            if len(topic_terms) >= max_terms:
                break

    if topic_terms:
        return topic_terms[:max_terms]
    return _extract_query_terms(cleaned, max_terms=max_terms)


def _normalize_weather_city_name(text: Optional[str], default: str = "") -> str:
    raw = str(text or "").strip()
    if not raw:
        return default

    city = urllib.parse.unquote(raw)
    city = re.sub(
        r"(今天|今日|明天|后天|昨天|昨日|今晚|今早|今晨|当前|现在|实时|最新|最近|这几天|这两天|本周|下周|周末|(?:下|本|这)?周[一二三四五六日天]|(?:下|本|这)?星期[一二三四五六日天]|(?:下|本|这)?礼拜[一二三四五六日天]|天天|当天)",
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


_WEATHER_DAY_ALIASES = {
    "今天": "今天",
    "今日": "今天",
    "明天": "明天",
    "后天": "后天",
    "昨天": "昨天",
    "昨日": "昨天",
}

_WEATHER_WEEKDAY_CHAR_MAP = {
    "一": "一",
    "二": "二",
    "三": "三",
    "四": "四",
    "五": "五",
    "六": "六",
    "日": "日",
    "天": "日",
}


def _normalize_weather_day_label(text: Optional[str], default: str = "") -> str:
    raw = str(text or "")
    picked: Optional[Tuple[int, int, str]] = None
    for token, normalized in _WEATHER_DAY_ALIASES.items():
        pos = raw.rfind(token)
        if pos < 0:
            continue
        candidate = (pos, len(token), normalized)
        if picked is None or candidate[0] > picked[0] or (candidate[0] == picked[0] and candidate[1] > picked[1]):
            picked = candidate

    weekday_picked: Optional[Tuple[int, str]] = None
    for match in re.finditer(r"(?:下|本|这)?(?:周|星期|礼拜)([一二三四五六日天])", raw):
        weekday_picked = (match.start(), _WEATHER_WEEKDAY_CHAR_MAP.get(match.group(1), match.group(1)))

    if weekday_picked and (picked is None or weekday_picked[0] >= picked[0]):
        return f"周{weekday_picked[1]}"
    if picked:
        return picked[2]
    return default

_EXCHANGE_CURRENCY_ALIASES = [
    ("CNY", "人民币", ("人民币", "cny", "rmb", "中国人民币")),
    ("JPY", "日元", ("日元", "日币", "jpy")),
    ("USD", "美元", ("美元", "usd", "美金", "美刀")),
    ("EUR", "欧元", ("欧元", "eur")),
    ("GBP", "英镑", ("英镑", "gbp")),
    ("HKD", "港币", ("港币", "港元", "hkd")),
    ("KRW", "韩元", ("韩元", "krw")),
    ("TWD", "新台币", ("新台币", "台币", "twd")),
    ("AUD", "澳元", ("澳元", "aud")),
    ("CAD", "加元", ("加元", "cad")),
    ("SGD", "新加坡元", ("新加坡元", "sgd")),
    ("CHF", "瑞士法郎", ("瑞士法郎", "chf")),
    ("THB", "泰铢", ("泰铢", "thb")),
]


def _detect_weather_target_day(text: Optional[str], default: str = "今天") -> str:
    return _normalize_weather_day_label(text, default=default)


def _looks_like_exchange_rate_query(text: Optional[str]) -> bool:
    raw = str(text or "")
    lowered = raw.lower()
    if any(token in lowered for token in ("汇率", "exchange rate", "currency converter", "货币转换", "兑换")):
        return True
    return bool(re.search(r"\b[a-z]{3}\s*(?:/|-|to|兑|对)\s*[a-z]{3}\b", lowered))


def _extract_exchange_rate_pair(text: Optional[str]) -> Optional[Tuple[str, str, str, str]]:
    raw = str(text or "")
    if not raw:
        return None

    code_to_name = {code: name for code, name, _ in _EXCHANGE_CURRENCY_ALIASES}
    explicit = re.search(r"\b([A-Z]{3})\s*(?:/|-|to|兑|对)\s*([A-Z]{3})\b", raw, flags=re.IGNORECASE)
    if explicit:
        base_code = explicit.group(1).upper()
        quote_code = explicit.group(2).upper()
        if base_code in code_to_name and quote_code in code_to_name:
            return base_code, quote_code, code_to_name[base_code], code_to_name[quote_code]

    lowered = raw.lower()
    hits: List[Tuple[int, int, str, str]] = []
    for code, display_name, aliases in _EXCHANGE_CURRENCY_ALIASES:
        best_pos: Optional[int] = None
        best_len = 0
        for alias in aliases:
            pos = lowered.find(alias.lower())
            if pos >= 0 and (best_pos is None or pos < best_pos):
                best_pos = pos
                best_len = len(alias)
        if best_pos is not None:
            hits.append((best_pos, best_len, code, display_name))

    hits.sort(key=lambda item: (item[0], -item[1]))
    ordered: List[Tuple[str, str]] = []
    seen = set()
    for _, _, code, display_name in hits:
        if code in seen:
            continue
        seen.add(code)
        ordered.append((code, display_name))
        if len(ordered) >= 2:
            break

    if len(ordered) >= 2:
        return ordered[0][0], ordered[1][0], ordered[0][1], ordered[1][1]
    return None


def _format_decimal_text(value: str) -> str:
    try:
        number = float(str(value).replace(",", "").strip())
    except Exception:
        return str(value).strip()
    decimals = 6 if abs(number) < 1 else 4
    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _exchange_rate_cache_key(base_code: str, quote_code: str) -> str:
    return f"{str(base_code or '').upper()}:{str(quote_code or '').upper()}"


def _get_cached_exchange_rate_result(base_code: str, quote_code: str) -> Optional[Dict[str, Any]]:
    cache_key = _exchange_rate_cache_key(base_code, quote_code)
    now_ts = datetime.now().timestamp()
    with _EXCHANGE_RATE_CACHE_LOCK:
        cached = _EXCHANGE_RATE_CACHE.get(cache_key)
        if not cached:
            return None
        expires_at = float(cached.get("expires_at") or 0)
        if expires_at <= now_ts:
            _EXCHANGE_RATE_CACHE.pop(cache_key, None)
            return None
        payload = cached.get("payload")
        return dict(payload) if isinstance(payload, dict) else None


def _set_cached_exchange_rate_result(base_code: str, quote_code: str, payload: Dict[str, Any]) -> None:
    cache_key = _exchange_rate_cache_key(base_code, quote_code)
    expires_at = datetime.now().timestamp() + EXCHANGE_RATE_CACHE_TTL_SECONDS
    with _EXCHANGE_RATE_CACHE_LOCK:
        _EXCHANGE_RATE_CACHE[cache_key] = {
            "expires_at": expires_at,
            "payload": dict(payload or {}),
        }


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


def _save_history_turn(
        user_id: str,
        session_id: str,
        func_type: str,
        user_message: str,
        assistant_message: str,
) -> Optional[Dict[str, Optional[int]]]:
    if user_id == "anonymous":
        return None
    return add_history_turn_to_supabase(
        user_id=user_id,
        session_id=session_id,
        func_type=func_type,
        user_content=user_message,
        assistant_content=assistant_message,
    )


async def _save_history_turn_async(
        user_id: str,
        session_id: str,
        func_type: str,
        user_message: str,
        assistant_message: str,
) -> Optional[Dict[str, Optional[int]]]:
    if user_id == "anonymous":
        return None
    return await asyncio.to_thread(
        _save_history_turn,
        user_id,
        session_id,
        func_type,
        user_message,
        assistant_message,
    )


async def _maybe_append_context_event_async(
        user_id: str,
        session_id: str,
        mode: str,
        model_id: str,
        model_backend: str,
        context_content: str,
        personalization: Dict[str, str],
) -> None:
    await asyncio.to_thread(
        _maybe_append_context_event,
        user_id,
        session_id,
        mode,
        model_id,
        model_backend,
        context_content,
        personalization,
    )


async def _maybe_store_long_term_hint_async(user_id: str, text: str) -> None:
    await asyncio.to_thread(_maybe_store_long_term_hint, user_id, text)


def _schedule_background_io(awaitable: "asyncio.Future[Any] | asyncio.Task[Any] | Any", label: str) -> None:
    async def _runner():
        try:
            await awaitable
        except Exception as e:
            print(f"⚠️ Background IO failed ({label}): {e}")

    try:
        asyncio.create_task(_runner())
    except RuntimeError:
        pass


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


def _make_context_compaction_key(
        user_id: str,
        session_id: str,
        mode: Optional[str],
        model_backend: str,
) -> str:
    return "|".join(
        [
            str(user_id or "").strip(),
            str(session_id or "").strip(),
            str(mode or "").strip().lower() or "general",
            str(model_backend or "local").strip().lower() or "local",
        ]
    )


def _claim_context_compaction(key: str) -> bool:
    with _CONTEXT_COMPACTION_LOCK:
        if key in _CONTEXT_COMPACTION_INFLIGHT:
            return False
        _CONTEXT_COMPACTION_INFLIGHT.add(key)
        return True


def _release_context_compaction(key: str) -> None:
    with _CONTEXT_COMPACTION_LOCK:
        _CONTEXT_COMPACTION_INFLIGHT.discard(key)


def _collect_context_compaction_snapshot(
        user_id: str,
        session_id: str,
        mode: Optional[str],
) -> Dict[str, Any]:
    if user_id == "anonymous":
        return {
            "payload": None,
            "needs_refresh": False,
            "source_text": "",
            "source_chars": 0,
            "source_messages": 0,
        }

    records = _read_recent_history_records(user_id, session_id, limit=CONTEXT_COMPACTION_SCAN_LIMIT)
    if not records:
        return {
            "payload": None,
            "needs_refresh": False,
            "source_text": "",
            "source_chars": 0,
            "source_messages": 0,
        }

    latest_payload = _latest_meta_event(records, "context_compaction")
    source_lines = _collect_compaction_source_lines(records, mode=mode)
    if not source_lines:
        return {
            "payload": latest_payload,
            "needs_refresh": False,
            "source_text": "",
            "source_chars": 0,
            "source_messages": 0,
        }

    source_text = "\n".join(source_lines).strip()
    source_chars = len(source_text)
    if source_chars < CONTEXT_COMPACTION_TRIGGER_CHARS:
        return {
            "payload": latest_payload,
            "needs_refresh": False,
            "source_text": source_text,
            "source_chars": source_chars,
            "source_messages": len(source_lines),
        }

    since_last = _messages_since_last_compaction(records)
    needs_refresh = (not latest_payload) or since_last >= CONTEXT_COMPACTION_MIN_INTERVAL
    return {
        "payload": latest_payload,
        "needs_refresh": needs_refresh,
        "source_text": source_text,
        "source_chars": source_chars,
        "source_messages": len(source_lines),
    }


def _refresh_context_compaction(
        user_id: str,
        session_id: str,
        mode: Optional[str],
        model_backend: str,
) -> Optional[Dict[str, Any]]:
    key = _make_context_compaction_key(user_id, session_id, mode, model_backend)
    if not _claim_context_compaction(key):
        return None

    try:
        snapshot = _collect_context_compaction_snapshot(user_id, session_id, mode)
        latest_payload = snapshot.get("payload")
        if not snapshot.get("needs_refresh"):
            return latest_payload

        source_text = str(snapshot.get("source_text") or "")
        if not source_text:
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

        raw = ask_llm(compact_prompt, model_type=model_backend)
        parsed = _safe_json_loads(raw)
        normalized = _normalize_compaction_payload(
            parsed,
            source_chars=int(snapshot.get("source_chars") or 0),
            source_messages=int(snapshot.get("source_messages") or 0),
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
        print(f"⚠️ Context compaction refresh failed: {e}")
        return None
    finally:
        _release_context_compaction(key)


async def _refresh_context_compaction_async(
        user_id: str,
        session_id: str,
        mode: Optional[str],
        model_backend: str,
) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(
        _refresh_context_compaction,
        user_id,
        session_id,
        mode,
        model_backend,
    )


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
    "jingyan.baidu.com",
    "csdn.net",  # 广告多，重复内容多 (视情况调整权重)
    "bilibili.com"  # 视频站对文本问答贡献通常较小，除非是专栏
]
SLOW_FETCH_DOMAINS = [
    "zhihu.com",
    "x.com",
    "twitter.com",
    "instagram.com",
    "linkedin.com",
    "reddit.com",
]
FAST_FETCH_PREFERRED_DOMAINS = [
    "openai.com",
    "weather.com.cn",
    "tianqi.com",
    "2345.com",
    "weather.cma.cn",
    "nmc.cn",
    "xe.com",
    "wise.com",
    "exchange-rates.org",
    "currencyrate.today",
    "shishihuilv.com",
    "money-converter.org",
    "finance.sina.com.cn",
    "xinhuanet.com",
    "people.com.cn",
    "reuters.com",
    "wikipedia.org",
]
EXCHANGE_RATE_PREFERRED_DOMAINS = [
    "xe.com",
    "wise.com",
    "exchange-rates.org",
    "currencyrate.today",
    "shishihuilv.com",
    "money-converter.org",
    "finance.sina.com.cn",
]

_SEARCH_HOST_RESOLUTION_CACHE: Dict[str, bool] = {}
_WEATHER_CITY_URL_CACHE: Dict[str, str] = {}
_EXCHANGE_RATE_CACHE: Dict[str, Dict[str, Any]] = {}
_EXCHANGE_RATE_CACHE_LOCK = threading.Lock()


def _result_text_fields(result: dict) -> Tuple[str, str, str]:
    title = str(result.get("title") or "")
    snippet = str(result.get("snippet") or "")
    link = str(result.get("link") or "")
    return title, snippet, link


def _count_term_hits_in_text(text: str, terms: List[str]) -> int:
    normalized_text = _normalize_match_text(text)
    hits = 0
    for term in terms:
        normalized_term = _normalize_match_text(term)
        if normalized_term and normalized_term in normalized_text:
            hits += 1
    return hits


def _topic_match_hit_count(result: dict, query_text: str, include_link: bool = True) -> int:
    topic_terms = _extract_topic_terms(query_text, max_terms=4)
    if not topic_terms:
        return 0
    title, snippet, link = _result_text_fields(result)
    hay = f"{title} {snippet} {link}" if include_link else f"{title} {snippet}"
    return _count_term_hits_in_text(hay, topic_terms)


def _is_low_signal_result(result: dict, query_text: str = "") -> bool:
    title, snippet, link = _result_text_fields(result)
    host = (urllib.parse.urlparse(link).netloc or "").lower().strip()
    if any(dom in host for dom in _LOW_SIGNAL_RESULT_HOSTS):
        if not any(token in query_text for token in ("下载", "安装", "素材", "设计", "导航", "平台", "官网")):
            return True
    if _is_fresh_search_query(query_text) and any(dom in host for dom in _FRESH_LOW_VALUE_HOSTS):
        if not any(re.search(pattern, f"{title} {snippet}", flags=re.IGNORECASE) for pattern in _NEWSY_RESULT_PATTERNS):
            return True
    hay = f"{title} {snippet}"
    if any(re.search(pattern, hay, flags=re.IGNORECASE) for pattern in _LOW_SIGNAL_RESULT_PATTERNS):
        if not any(token in query_text for token in ("下载", "安装", "素材", "设计", "导航", "平台", "官网")):
            return True
    return False


def _is_topically_relevant_search_result(result: dict, query_text: str) -> bool:
    topic_terms = _extract_topic_terms(query_text, max_terms=4)
    if not topic_terms:
        return True

    title, snippet, link = _result_text_fields(result)
    title_snippet_hits = _count_term_hits_in_text(f"{title} {snippet}", topic_terms)
    full_hits = _count_term_hits_in_text(f"{title} {snippet} {link}", topic_terms)
    if _is_reason_search_query(query_text):
        if not re.search(r"(原因|为何|为什么|背后|动因|逻辑|布局|战略|解析|解读|造车)", f"{title} {snippet}", flags=re.IGNORECASE):
            return False

    if len(topic_terms) == 1:
        return title_snippet_hits >= 1 or full_hits >= 1
    return title_snippet_hits >= 2 or full_hits >= 2


def _score_search_results_quality(results: List[dict], query_text: str) -> float:
    if not results:
        return 0.0

    score = 0.0
    for idx, row in enumerate(results[:4]):
        weight = max(1.0, 4.0 - idx)
        if _is_low_signal_result(row, query_text):
            score -= 6.0 * weight
            continue
        score += float(row.get("_score", 0.0)) * (0.18 * weight)
        if _is_topically_relevant_search_result(row, query_text):
            score += 8.0 * weight
            score += 2.0 * min(3, _topic_match_hit_count(row, query_text, include_link=False))
        else:
            score -= 8.0 * weight
    return score


def _build_search_query_variants(query: str, prefer_fresh: bool = False) -> List[str]:
    raw = str(query or "").strip()
    if not raw:
        return []

    cleaned = _light_clean_search_query(raw)
    topic_terms = _extract_topic_terms(cleaned, max_terms=4)
    variants = _dedupe_preserve_order([raw, cleaned])

    if topic_terms:
        if _is_reason_search_query(cleaned):
            enriched_topics = [term for term in topic_terms if term not in {"汽车", "车"}]
            if any(token in cleaned for token in ("汽车", "造车")):
                enriched_topics.append("造车")
            variants.extend(
                _dedupe_preserve_order(
                    [
                        " ".join(_dedupe_preserve_order(enriched_topics + ["原因"])),
                    ]
                )
            )
        if prefer_fresh or _is_fresh_search_query(cleaned):
            variants.extend(
                _dedupe_preserve_order(
                    [
                        " ".join(_dedupe_preserve_order(topic_terms + ["最新", "动态"])),
                        " ".join(_dedupe_preserve_order(topic_terms + ["最新", "进展"])),
                    ]
                )
            )

    return _dedupe_preserve_order(variants)


def _build_searxng_engine_groups(query: str = "", prefer_fresh: bool = False) -> List[str]:
    engines = [engine.strip() for engine in SEARXNG_ENGINES.split(",") if engine.strip()]
    if not engines:
        return [""]

    groups: List[str] = []
    seen = set()

    def add(group: List[str]) -> None:
        normalized = [item.strip() for item in group if item and item.strip()]
        if not normalized:
            return
        key = ",".join(normalized)
        if key in seen:
            return
        seen.add(key)
        groups.append(key)

    preferred: List[str] = []
    if prefer_fresh or _is_fresh_search_query(query):
        preferred.extend([engine for engine in ("bing", "bing news", "wikipedia", "sogou") if engine in engines])
    else:
        preferred.extend([engine for engine in ("bing", "wikipedia", "sogou", "bing news") if engine in engines])
    preferred.extend([engine for engine in engines if engine not in preferred])

    add(preferred or engines)
    add(engines)
    for removable in ("duckduckgo", "baidu", "sogou", "wikipedia", "bing news"):
        if removable in engines:
            add([item for item in engines if item != removable])
    if "bing" in engines and "sogou" in engines:
        add(["bing", "sogou", "wikipedia"])
        add(["bing", "sogou"])
    if "bing" in engines and "bing news" in engines:
        add(["bing", "bing news", "wikipedia"])
        add(["bing", "bing news"])
    if "bing" in engines:
        add(["bing", "wikipedia"])
        add(["bing"])
    if "sogou" in engines:
        add(["sogou"])
    if "baidu" in engines:
        add(["baidu"])
    return groups


def _calculate_result_score(result: dict, query_keywords: List[str], query_text: str = "") -> float:
    """Calculate a relevance score for one search result."""
    score = 0.0
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    link = result.get("link", "").lower()
    normalized_hay = _normalize_match_text(f"{title} {snippet} {link}")
    cleaned_query = _light_clean_search_query(query_text)
    normalized_query = _normalize_match_text(cleaned_query)
    matched_terms = 0
    title_hits = 0
    is_fresh_query = _is_fresh_search_query(query_text)
    is_reason_query = _is_reason_search_query(query_text)
    topic_terms = _extract_topic_terms(query_text, max_terms=4)
    topical_hits = _count_term_hits_in_text(f"{title} {snippet}", topic_terms) if topic_terms else 0

    # 1. 标题关键词加权
    for kw in query_keywords:
        kw = kw.lower()
        normalized_kw = _normalize_match_text(kw)
        if not normalized_kw:
            continue
        if normalized_kw in _normalize_match_text(title):
            score += 3.0  # 标题包含关键词权重高
            matched_terms += 1
            title_hits += 1
            continue
        if normalized_kw in _normalize_match_text(snippet):
            score += 1.0  # 摘要包含关键词
            matched_terms += 1
            continue
        if normalized_kw in normalized_hay:
            score += 0.6
            matched_terms += 1

    if matched_terms == 0:
        score -= 6.0
    else:
        score += min(6.0, matched_terms * 1.4)
    if title_hits >= 2:
        score += 3.0
    if normalized_query and len(normalized_query) >= 4 and normalized_query in normalized_hay:
        score += 6.0

    if topic_terms:
        if topical_hits == 0:
            score -= 12.0
        elif len(topic_terms) >= 2 and topical_hits == 1:
            score -= 5.0
        else:
            score += min(6.0, topical_hits * 2.5)

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
                score -= 6.0
    if _is_low_signal_result(result, query_text):
        score -= 12.0
    if "zhihu.com" in link and not any(token in query_text for token in _SUBJECTIVE_QUERY_HINTS):
        score -= 4.0
    if is_fresh_query:
        if any(dom in link for dom in _FRESH_LOW_VALUE_HOSTS):
            score -= 10.0
        if any(dom in link for dom in ("baike.baidu.com", "wikipedia.org", "zhidao.baidu.com", "wenku.baidu.com", "zhihu.com")):
            score -= 5.0
        if any(re.search(pattern, f"{title} {snippet}", flags=re.IGNORECASE) for pattern in _NEWSY_RESULT_PATTERNS):
            score += 4.0
    if is_reason_query:
        if re.search(r"(推荐|选购|参数对比|评测|开箱|配置|购买|值得买|平板|手机推荐)", f"{title} {snippet}", flags=re.IGNORECASE):
            score -= 6.0
        if re.search(r"(原因|为何|为什么|造车|战略|布局|解析|背后|动因)", f"{title} {snippet}", flags=re.IGNORECASE):
            score += 4.0

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
        score = _calculate_result_score(r, keywords, query)
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
    if not _is_valid_search_result_link(link):
        return None
    return normalized


def _is_valid_search_result_link(link: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(link or "").strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    path = (parsed.path or "").strip().lower()
    if not host:
        return False

    if host in {"www.baidu.com", "baidu.com", "m.baidu.com"} and path in {"", "/", "/index.htm", "/cache", "/cache/"}:
        return False
    if host in {"www.sogou.com", "sogou.com"} and path in {"", "/", "/web"}:
        return False
    if host in {"www.sogou.com", "sogou.com"} and path.startswith("/antispider"):
        return False
    if host == "m.sogou.com" and path.startswith("/h5/pages/video-recommend"):
        return False
    if host in {"www.bing.com", "bing.com", "cn.bing.com"} and path in {"", "/", "/search"}:
        return False

    cached = _SEARCH_HOST_RESOLUTION_CACHE.get(host)
    if cached is not None:
        return cached

    try:
        resolved_hosts = {
            info[4][0]
            for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            if info and info[4]
        }
        if not resolved_hosts:
            _SEARCH_HOST_RESOLUTION_CACHE[host] = False
            return False
        for resolved in resolved_hosts:
            ip = ipaddress.ip_address(resolved)
            if not ip.is_global:
                _SEARCH_HOST_RESOLUTION_CACHE[host] = False
                return False
    except Exception:
        _SEARCH_HOST_RESOLUTION_CACHE[host] = False
        return False

    _SEARCH_HOST_RESOLUTION_CACHE[host] = True
    return True


def _rewrite_search_query_for_searxng(query: str, history_text: str = "") -> str:
    raw_query = str(query or "")
    cleaned = re.sub(r"[\"'`]+", " ", raw_query)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip() or raw_query.strip()
    if not cleaned:
        return cleaned

    lowered = cleaned.lower()
    if _is_profile_query(raw_query):
        subject = _extract_profile_subject(raw_query)
        if subject:
            return f"{subject} 简介"

    if any(k in lowered for k in ["天气", "气温", "温度", "weather", "forecast"]):
        target_day = _detect_weather_target_day(cleaned, default="")
        if not target_day:
            target_day = _detect_weather_target_day(history_text, default="")
        city = _normalize_weather_city_name(cleaned, default="")
        if not city:
            city = _normalize_weather_city_name(history_text, default="")
        city = _normalize_weather_city_name(city, default="")
        if city:
            parts = [city]
            if target_day:
                parts.append(target_day)
            parts.extend(["天气", "预报"])
            return " ".join(parts)

    if _looks_like_exchange_rate_query(cleaned):
        pair = _extract_exchange_rate_pair(cleaned)
        if pair:
            base_code, quote_code, _, _ = pair
            return f"{base_code} {quote_code} 汇率"

    return cleaned


def _build_weather_fallback_items(query_text: str) -> List[dict]:
    city = _normalize_weather_city_name(query_text, default="")
    if not city:
        return []

    cached_url = _lookup_weather_page_url(city)

    if not cached_url:
        return []

    return [{
        "title": f"{city}天气预报",
        "link": cached_url,
        "snippet": f"{city}天气预报与未来几天天气趋势",
        "source": "weather.com.cn",
        "provider": "weather-fallback",
    }]


def _lookup_weather_page_url(city: str) -> str:
    normalized_city = _normalize_weather_city_name(city, default="")
    if not normalized_city:
        return ""

    cached_url = _WEATHER_CITY_URL_CACHE.get(normalized_city)
    if cached_url:
        return cached_url

    try:
        import requests

        resp = requests.get(
            "https://toy1.weather.com.cn/search",
            params={"cityname": normalized_city},
            headers={
                "Referer": "https://www.weather.com.cn/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            },
            timeout=max(6, SEARXNG_TIMEOUT_SECONDS),
        )
        if resp.status_code != 200:
            return ""

        body = resp.text or ""
        start = body.find("[")
        end = body.rfind("]")
        if start < 0 or end <= start:
            return ""

        payload = json.loads(body[start:end + 1])
        if not isinstance(payload, list):
            return ""

        picked_code = ""
        for item in payload:
            ref = str((item or {}).get("ref") or "").strip()
            if not ref:
                continue
            parts = ref.split("~")
            city_code = parts[0].strip() if parts else ""
            city_label = parts[2].strip() if len(parts) > 2 else ""
            province_label = parts[-1].strip() if parts else ""
            if city_label == normalized_city or province_label == normalized_city:
                picked_code = city_code
                break
            if not picked_code:
                picked_code = city_code
        if not picked_code:
            return ""

        cached_url = f"https://www.weather.com.cn/weather/{picked_code}.shtml"
        _WEATHER_CITY_URL_CACHE[normalized_city] = cached_url
        return cached_url
    except Exception as e:
        print(f"⚠️ [Search] weather fallback lookup failed: {e}")
        return ""


def _build_exchange_fallback_items(query_text: str) -> List[dict]:
    pair = _extract_exchange_rate_pair(query_text)
    if not pair:
        return []

    base_code, quote_code, _, _ = pair
    return [
        {
            "title": f"{base_code}/{quote_code} 汇率 - XE",
            "link": f"https://www.xe.com/zh-CN/currencyconverter/convert/?Amount=1&From={base_code}&To={quote_code}",
            "snippet": f"{base_code} 兑 {quote_code} 实时汇率",
            "source": "xe.com",
            "provider": "exchange-fallback",
        },
        {
            "title": f"{base_code}/{quote_code} 汇率 - Exchange Rates",
            "link": f"https://www.exchange-rates.org/zh/converter/{base_code.lower()}-{quote_code.lower()}",
            "snippet": f"{base_code} 兑 {quote_code} 汇率换算",
            "source": "exchange-rates.org",
            "provider": "exchange-fallback",
        },
        {
            "title": f"{base_code}/{quote_code} 汇率 - Wise",
            "link": f"https://wise.com/zh-cn/currency-converter/{base_code.lower()}-to-{quote_code.lower()}-rate",
            "snippet": f"{base_code} 兑 {quote_code} 中间市场汇率",
            "source": "wise.com",
            "provider": "exchange-fallback",
        },
    ]


def _build_domain_fallback_fetch_items(query_text: str, domain: str) -> List[dict]:
    if domain == "weather":
        return _build_weather_fallback_items(query_text)
    if domain == "exchange":
        return _build_exchange_fallback_items(query_text)
    if domain == "profile":
        subject = _extract_profile_subject(query_text)
        if not subject:
            return []

        variants: List[str] = []

        def _add_variant(val: str) -> None:
            candidate = re.sub(r"\s{2,}", " ", str(val or "")).strip()
            if candidate and candidate not in variants:
                variants.append(candidate)

        _add_variant(subject)
        if subject.endswith("公司"):
            _add_variant(f"{subject[:-2]}集团")
        elif subject.endswith("集团"):
            _add_variant(f"{subject[:-2]}公司")
        elif len(subject) <= 10:
            _add_variant(f"{subject}公司")
            _add_variant(f"{subject}集团")

        items: List[dict] = []
        for variant in variants[:4]:
            quoted = urllib.parse.quote(variant, safe="")
            items.append(
                {
                    "title": f"{variant} - 百度百科",
                    "link": f"https://baike.baidu.com/item/{quoted}",
                    "snippet": f"{variant} 的百科介绍页面",
                    "provider": "profile-fallback",
                }
            )
            items.append(
                {
                    "title": f"{variant} - 维基百科",
                    "link": f"https://zh.wikipedia.org/wiki/{quoted}",
                    "snippet": f"{variant} 的维基百科页面",
                    "provider": "profile-fallback",
                }
            )
        return items
    return []


def _pick_search_fetch_items(results: List[dict], query: str, limit: int, domain: str = "") -> List[dict]:
    if not results:
        return []

    query_terms = _extract_query_terms(query, max_terms=8)
    scored: List[Tuple[float, int, dict]] = []
    for idx, item in enumerate(results):
        link = str(item.get("link") or "").strip()
        if not link:
            continue
        host = (urllib.parse.urlparse(link).netloc or "").lower().strip()
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        hay = _normalize_match_text(f"{title} {snippet} {host}")
        score = float(item.get("_score", 0.0)) + max(0.0, 20.0 - idx * 2.5)
        if any(dom in host for dom in FAST_FETCH_PREFERRED_DOMAINS):
            score += 18.0
        if any(dom in host for dom in SLOW_FETCH_DOMAINS):
            score -= 24.0
        if domain == "weather":
            if any(dom in host for dom in ("weather.com.cn", "tianqi.com", "2345.com", "weather.cma.cn", "nmc.cn")):
                score += 32.0
            else:
                score -= 12.0
        if domain == "exchange":
            if any(dom in host for dom in EXCHANGE_RATE_PREFERRED_DOMAINS):
                score += 36.0
            elif any(dom in host for dom in ("jingyan.baidu.com", "zhidao.baidu.com", "wenku.baidu.com")):
                score -= 40.0
            else:
                score -= 8.0
        if domain == "profile":
            if any(dom in host for dom in ("baike.baidu.com", "wikipedia.org")):
                score += 38.0
            if any(dom in host for dom in ("zhihu.com", "zhidao.baidu.com", "wenku.baidu.com", "jingyan.baidu.com")):
                score -= 18.0
            if any(noise in hay for noise in _PROFILE_NOISE_KEYWORDS):
                score -= 24.0
        for term in query_terms[:4]:
            tn = _normalize_match_text(term)
            if tn and tn in hay:
                score += 2.0
        scored.append((score, idx, item))

    scored.sort(key=lambda x: (-x[0], x[1]))
    picked: List[dict] = []
    seen = set()
    for _, _, item in scored:
        key = _canonicalize_link(str(item.get("link") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def _build_direct_weather_answer(city_name: str, pages: List[Dict[str, Any]]) -> str:
    target_day = _detect_weather_target_day(city_name, default="今天")
    weather_values: Dict[str, str] = {}
    citations: Dict[str, int] = {}

    for idx, page in enumerate(pages[:2], start=1):
        for raw_line in str(page.get("content") or "").splitlines():
            line = str(raw_line or "").strip()
            if not line or ":" not in line:
                continue
            key, value = [part.strip() for part in line.split(":", 1)]
            if not key or not value:
                continue
            normalized_key = ""
            if key == "更新时间":
                normalized_key = "更新时间"
            else:
                normalized = key.replace("今日", "今天")
                if normalized.startswith(target_day):
                    normalized_key = normalized[len(target_day):].strip()
                elif target_day == "今天":
                    if normalized == "今天天气":
                        normalized_key = "天气"
                    elif normalized in {"天气", "当前温度", "最高/最低气温", "风力"}:
                        normalized_key = normalized
            if normalized_key and normalized_key not in weather_values:
                weather_values[normalized_key] = value
                citations[normalized_key] = idx

    if not weather_values:
        return ""

    city = _normalize_weather_city_name(city_name, default="当地")
    parts = [f"{city}{target_day}"]
    if weather_values.get("天气"):
        parts.append(f"天气{weather_values['天气']}[{citations.get('天气', 1)}]")
    if weather_values.get("当前温度"):
        parts.append(f"当前温度{weather_values['当前温度']}[{citations.get('当前温度', 1)}]")
    if weather_values.get("最高/最低气温"):
        parts.append(f"最高/最低气温{weather_values['最高/最低气温']}[{citations.get('最高/最低气温', 1)}]")
    if weather_values.get("风力"):
        parts.append(f"风力{weather_values['风力']}[{citations.get('风力', 1)}]")
    if weather_values.get("更新时间"):
        parts.append(f"更新时间{weather_values['更新时间']}[{citations.get('更新时间', 1)}]")

    summary = "，".join(parts).strip("，")
    if not summary.endswith("。"):
        summary += "。"
    return summary


def _build_direct_exchange_answer(query_text: str, pages: List[Dict[str, Any]]) -> str:
    pair = _extract_exchange_rate_pair(query_text)
    if not pair:
        return ""

    base_code, quote_code, base_name, quote_name = pair
    direct_rate = ""
    reverse_rate = ""
    direct_citation = 1
    reverse_citation = 1
    updated_at = ""
    update_citation = 1

    for idx, page in enumerate(pages[:2], start=1):
        for raw_line in str(page.get("content") or "").splitlines():
            line = str(raw_line or "").strip()
            if not line or ":" not in line:
                continue
            key, value = [part.strip() for part in line.split(":", 1)]
            if key == "更新时间" and value and not updated_at:
                updated_at = value
                update_citation = idx
                continue

            pair_match = re.fullmatch(r"1 ([A-Z]{3})", key)
            value_match = re.match(r"([0-9][0-9.,]*)\s*([A-Z]{3})", value)
            if not pair_match or not value_match:
                continue

            src_code = pair_match.group(1).upper()
            rate_text = value_match.group(1).replace(",", "")
            dst_code = value_match.group(2).upper()

            if src_code == base_code and dst_code == quote_code and not direct_rate:
                direct_rate = rate_text
                direct_citation = idx
            elif src_code == quote_code and dst_code == base_code and not reverse_rate:
                reverse_rate = rate_text
                reverse_citation = idx

    if not direct_rate and reverse_rate:
        try:
            direct_rate = str(1 / float(reverse_rate))
            direct_citation = reverse_citation
        except Exception:
            direct_rate = ""
    if not reverse_rate and direct_rate:
        try:
            reverse_rate = str(1 / float(direct_rate))
            reverse_citation = direct_citation
        except Exception:
            reverse_rate = ""

    if not direct_rate:
        return ""

    parts = [
        f"按当前抓取到的汇率，1{base_name}约等于{_format_decimal_text(direct_rate)}{quote_name}[{direct_citation}]"
    ]
    if reverse_rate:
        parts.append(
            f"1{quote_name}约等于{_format_decimal_text(reverse_rate)}{base_name}[{reverse_citation}]"
        )
    if updated_at:
        parts.append(f"更新时间{updated_at}[{update_citation}]")

    summary = "，".join(parts).strip("，")
    if not summary.endswith("。"):
        summary += "。"
    return summary


def _build_direct_market_tool_answer(result: Dict[str, Any], domain: str = "") -> str:
    if not result:
        return ""

    subject = str(result.get("title") or "").replace(" 实时报价", "").strip() or "当前行情"
    snippet = str(result.get("snippet") or "").strip()
    if not snippet:
        return ""

    facts: Dict[str, str] = {}
    for raw_part in snippet.split("|"):
        part = str(raw_part or "").strip()
        if not part or ":" not in part:
            continue
        key, value = [seg.strip() for seg in part.split(":", 1)]
        if key and value and key not in facts:
            facts[key] = value

    if not facts:
        return ""

    parts: List[str] = []
    if domain == "stock":
        if facts.get("最新价"):
            parts.append(f"{subject}当前最新价{facts['最新价']}[1]")
        if facts.get("涨跌"):
            parts.append(f"涨跌{facts['涨跌']}[1]")
        if facts.get("今开"):
            parts.append(f"今开{facts['今开']}[1]")
        if facts.get("高/低"):
            parts.append(f"高/低{facts['高/低']}[1]")
        if facts.get("时间"):
            parts.append(f"时间{facts['时间']}[1]")
    elif domain == "gold":
        if facts.get("最新报价"):
            parts.append(f"{subject}当前最新报价{facts['最新报价']}[1]")
        if facts.get("前收"):
            parts.append(f"前收{facts['前收']}[1]")
        if facts.get("高/低"):
            parts.append(f"高/低{facts['高/低']}[1]")
        if facts.get("时间"):
            parts.append(f"时间{facts['时间']}[1]")
    else:
        if facts.get("最新价"):
            parts.append(f"{subject}当前最新价{facts['最新价']}[1]")
        elif facts.get("最新报价"):
            parts.append(f"{subject}当前最新报价{facts['最新报价']}[1]")
        for key in ("涨跌", "今开", "高/低", "时间"):
            if facts.get(key):
                parts.append(f"{key}{facts[key]}[1]")

    if not parts:
        return ""

    summary = "，".join(parts).strip("，")
    if not summary.endswith("。"):
        summary += "。"
    return summary


def tool_get_exchange_rate(query: str) -> List[dict]:
    """Get realtime exchange rate via lightweight APIs instead of webpage scraping."""
    import requests

    pair = _extract_exchange_rate_pair(query)
    if not pair:
        return []

    base_code, quote_code, _, _ = pair
    cached = _get_cached_exchange_rate_result(base_code, quote_code)
    if cached:
        return [cached]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    }
    providers = [
        {
            "name": "ExchangeRate-API",
            "link": f"https://open.er-api.com/v6/latest/{base_code}",
            "fetch": lambda: _fetch_exchange_rate_from_er_api(base_code, quote_code, headers),
        },
        {
            "name": "Frankfurter",
            "link": f"https://api.frankfurter.app/latest?from={base_code}&to={quote_code}",
            "fetch": lambda: _fetch_exchange_rate_from_frankfurter(base_code, quote_code, headers),
        },
    ]

    for provider in providers:
        try:
            rate_text, reverse_rate_text, updated_at = provider["fetch"]()
        except Exception as e:
            print(f"⚠️ [Exchange Tool] provider={provider['name']} failed: {e}")
            continue

        if not rate_text:
            continue

        content_lines = [f"1 {base_code}: {rate_text} {quote_code}"]
        snippet_parts = [f"1 {base_code}: {rate_text} {quote_code}"]
        if reverse_rate_text:
            content_lines.append(f"1 {quote_code}: {reverse_rate_text} {base_code}")
            snippet_parts.append(f"1 {quote_code}: {reverse_rate_text} {base_code}")
        if updated_at:
            content_lines.append(f"更新时间: {updated_at}")
            snippet_parts.append(f"更新时间: {updated_at}")

        payload = {
            "type": "web",
            "title": f"{base_code}/{quote_code} 汇率",
            "link": provider["link"],
            "snippet": " | ".join(snippet_parts),
            "source": provider["name"],
            "date": updated_at,
            "provider": f"exchange-api-{provider['name'].lower()}",
            "content": "\n".join(content_lines),
        }
        _set_cached_exchange_rate_result(base_code, quote_code, payload)
        return [payload]

    return []


def _normalize_exchange_rate_updated_at(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text

    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass

    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return text


def _fetch_exchange_rate_from_frankfurter(
    base_code: str,
    quote_code: str,
    headers: Dict[str, str],
) -> Tuple[str, str, str]:
    import requests

    api_url = f"https://api.frankfurter.app/latest?from={base_code}&to={quote_code}"
    resp = requests.get(api_url, headers=headers, timeout=EXCHANGE_RATE_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json() or {}
    rates = data.get("rates") or {}
    rate = rates.get(quote_code)
    if rate in (None, ""):
        raise ValueError("No rate returned")

    direct_rate = _format_decimal_text(str(rate))
    reverse_rate = ""
    try:
        numeric = float(str(rate).replace(",", "").strip())
        if numeric:
            reverse_rate = _format_decimal_text(str(1 / numeric))
    except Exception:
        reverse_rate = ""
    updated_at = _normalize_exchange_rate_updated_at(data.get("date"))
    return direct_rate, reverse_rate, updated_at


def _fetch_exchange_rate_from_er_api(
    base_code: str,
    quote_code: str,
    headers: Dict[str, str],
) -> Tuple[str, str, str]:
    import requests

    api_url = f"https://open.er-api.com/v6/latest/{base_code}"
    resp = requests.get(api_url, headers=headers, timeout=EXCHANGE_RATE_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json() or {}
    if str(data.get("result") or "").lower() != "success":
        raise ValueError(f"Unexpected result: {data.get('result')}")
    rates = data.get("rates") or {}
    rate = rates.get(quote_code)
    if rate in (None, ""):
        raise ValueError("No rate returned")

    direct_rate = _format_decimal_text(str(rate))
    reverse_rate = ""
    try:
        numeric = float(str(rate).replace(",", "").strip())
        if numeric:
            reverse_rate = _format_decimal_text(str(1 / numeric))
    except Exception:
        reverse_rate = ""

    updated_at = (
        str(data.get("time_last_update_utc") or "").strip()
        or str(data.get("time_last_update_unix") or "").strip()
    )
    return direct_rate, reverse_rate, _normalize_exchange_rate_updated_at(updated_at)


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

    filtered = [row for row in normalized if not _is_low_signal_result(row, query)]
    if filtered:
        normalized = filtered

    topic_terms = _extract_topic_terms(query, max_terms=4)
    if topic_terms:
        strict_topic_hits = [row for row in normalized if _is_topically_relevant_search_result(row, query)]
        if strict_topic_hits:
            normalized = strict_topic_hits

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


def _search_with_searxng(query: str, max_results: int, prefer_fresh: bool = False) -> List[dict]:
    import requests

    if not SEARXNG_BASE_URL:
        return []

    chosen_language = _choose_searxng_language(query)
    endpoint = f"{SEARXNG_BASE_URL}/search"
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    }
    if chosen_language:
        headers["Accept-Language"] = chosen_language

    parse_limit = max(24, max_results * 4)
    for engine_group in _build_searxng_engine_groups(query, prefer_fresh=prefer_fresh):
        params: Dict[str, Any] = {
            "q": query,
            "format": "json",
            "safesearch": SEARXNG_SAFESEARCH,
            "pageno": 1,
        }
        if chosen_language:
            params["language"] = chosen_language
        if engine_group:
            params["engines"] = engine_group
        if prefer_fresh:
            params["time_range"] = "day"
            params["categories"] = "general,news"

        try:
            resp = requests.get(endpoint, params=params, headers=headers, timeout=SEARXNG_TIMEOUT_SECONDS)
        except Exception as e:
            print(f"⚠️ [SearXNG] engines={engine_group or '(default)'} request failed: {e}")
            continue
        if resp.status_code != 200:
            print(f"⚠️ [SearXNG] Error {resp.status_code}: {resp.text[:240]}")
            continue

        payload = resp.json() or {}
        rows = payload.get("results", []) or []
        unresponsive = payload.get("unresponsive_engines") or []
        parsed: List[dict] = []
        for row in rows:
            if len(parsed) >= parse_limit:
                break
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            link = str(row.get("url") or "").strip()
            snippet = re.sub(r"\s+", " ", str(row.get("content") or row.get("snippet") or "")).strip()
            if not title or not link:
                continue
            parsed.append({
                "title": title,
                "link": link,
                "snippet": snippet,
                "source": str(row.get("engine") or "").strip(),
                "date": str(row.get("publishedDate") or row.get("publishedDateText") or row.get("pubdate") or "").strip(),
                "provider": "searxng",
            })
        if parsed:
            return parsed
        if unresponsive:
            print(f"⚠️ [SearXNG] engines={engine_group or '(default)'} unresponsive={unresponsive}")
    return []


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
    """Get structured weather forecast, falling back to Moji when needed."""
    import requests
    from bs4 import BeautifulSoup

    results: List[dict] = []
    raw_query = str(city_name or "").strip()
    print(f"☁️ [Weather Tool] Getting weather for: {raw_query}")

    normalized_city = _normalize_weather_city_name(raw_query, default="北京")
    target_day = _detect_weather_target_day(raw_query, default="今天")
    page_url = _lookup_weather_page_url(normalized_city)

    if page_url:
        try:
            headers = {
                "Referer": "https://www.weather.com.cn/",
                "User-Agent": "Mozilla/5.0",
            }
            page_resp = requests.get(page_url, headers=headers, timeout=10)
            if page_resp.status_code == 200:
                html = page_resp.content.decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, "html.parser")

                update_node = soup.select_one("#update_time")
                update_text = ""
                if update_node and update_node.get("value"):
                    update_text = str(update_node.get("value") or "").strip()

                content_lines: List[str] = []
                snippet_parts: List[str] = []
                target_found = False
                day_nodes = soup.select("ul.t.clearfix li.sky")

                for idx, day_node in enumerate(day_nodes[:7]):
                    heading = day_node.select_one("h1")
                    label_text = heading.get_text(" ", strip=True) if heading else ""
                    day_label = _normalize_weather_day_label(label_text, default="")
                    if not day_label:
                        day_label = label_text or ("今天" if idx == 0 else "")
                    if not day_label:
                        continue

                    weather_node = day_node.select_one("p.wea")
                    weather_text = (
                        str(weather_node.get("title") or "").strip()
                        if weather_node and weather_node.get("title")
                        else (weather_node.get_text(" ", strip=True) if weather_node else "")
                    )

                    tem_node = day_node.select_one("p.tem")
                    high_node = tem_node.select_one("span") if tem_node else None
                    low_node = tem_node.select_one("i") if tem_node else None
                    high_text = high_node.get_text(" ", strip=True) if high_node else ""
                    low_text = low_node.get_text(" ", strip=True) if low_node else ""
                    temp_text = ""
                    if high_text or low_text:
                        if low_text and "℃" not in low_text:
                            low_text = f"{low_text}℃"
                        temp_text = f"{high_text}/{low_text}".strip("/")

                    win_node = day_node.select_one("p.win")
                    wind_titles = [
                        str(span.get("title") or "").strip()
                        for span in (win_node.select("em span") if win_node else [])
                        if str(span.get("title") or "").strip()
                    ]
                    wind_force_node = win_node.select_one("i") if win_node else None
                    wind_force = wind_force_node.get_text(" ", strip=True) if wind_force_node else ""
                    wind_text = ""
                    if wind_titles:
                        wind_text = "转".join(wind_titles[:2]) if len(wind_titles) >= 2 else wind_titles[0]
                    if wind_force:
                        wind_text = f"{wind_text} {wind_force}".strip()

                    if weather_text:
                        content_lines.append(f"{day_label}天气: {weather_text}")
                    if temp_text:
                        content_lines.append(f"{day_label}最高/最低气温: {temp_text}")
                    if wind_text:
                        content_lines.append(f"{day_label}风力: {wind_text}")

                    if day_label == target_day and not target_found:
                        if weather_text:
                            snippet_parts.append(f"天气: {weather_text}")
                        if temp_text:
                            snippet_parts.append(f"最高/最低气温: {temp_text}")
                        if wind_text:
                            snippet_parts.append(f"风力: {wind_text}")
                        target_found = True

                if update_text:
                    content_lines.append(f"更新时间: {update_text}")
                    if target_found:
                        snippet_parts.append(f"更新时间: {update_text}")

                if content_lines:
                    if not snippet_parts:
                        if update_text:
                            snippet_parts.append(f"更新时间: {update_text}")
                    results.append({
                        "type": "web",
                        "title": f"{normalized_city}{target_day}天气预报",
                        "link": page_url,
                        "snippet": " | ".join(snippet_parts) or f"{normalized_city}{target_day}天气预报",
                        "source": "weather.com.cn",
                        "date": update_text,
                        "provider": "weather-official",
                        "content": "\n".join(content_lines),
                    })
                    return results
        except Exception as e:
            print(f"⚠️ [Weather Tool/Official] Failed: {e}")

    return _tool_get_weather_moji_fallback(raw_query)


def _tool_get_weather_moji_fallback(city_name: str) -> List[dict]:
    """Fallback realtime weather from Moji."""
    import requests
    import json as _json
    from bs4 import BeautifulSoup

    results: List[dict] = []
    print(f"☁️ [Weather Tool/Moji] Fallback for: {city_name}")

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
        stock_like_markets = {"11", "12", "31", "41", "71", "73", "103"}
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
        query_has_chinese = bool(re.search(r"[\u4e00-\u9fff]", raw_query))
        market_hint_text = raw_query.lower()
        fullwidth_ascii_map = str.maketrans({
            "－": "-",
            "Ｗ": "W",
            "Ｒ": "R",
        })
        normalized_cleaned_query = cleaned_query.translate(fullwidth_ascii_map)

        def _parse_num(value: Any) -> float:
            try:
                return float(str(value or "").replace(",", "").strip())
            except Exception:
                return 0.0

        def _quote_has_usable_price(code: str, values: List[str]) -> bool:
            if code.startswith(("sh", "sz")) and len(values) > 31:
                return _parse_num(values[3]) > 0
            if code.startswith(("rt_hk", "hk")) and len(values) > 18:
                numeric_fields = [_parse_num(values[idx]) for idx in (2, 3, 4, 5, 6)]
                return any(v > 0 for v in numeric_fields)
            if code.startswith("gb_") and len(values) > 7:
                numeric_fields = [_parse_num(values[idx]) for idx in (1, 4, 5, 6)]
                return any(v > 0 for v in numeric_fields)
            numeric_fields = [_parse_num(v) for v in values[:8]]
            return any(v > 0 for v in numeric_fields)

        code_match = re.search(r"\b(?:sh|sz|hk)?\d{5,6}\b", raw_query.lower())
        us_match = re.search(r"\b[A-Za-z]{1,6}\b", raw_query)
        if code_match:
            direct_code = code_match.group(0).lower()
            if direct_code.isdigit():
                if len(direct_code) == 6:
                    direct_code = ("sh" if direct_code.startswith("6") else "sz") + direct_code
                elif len(direct_code) == 5:
                    direct_code = "hk" + direct_code
        elif (
            us_match
            and len(raw_query.strip()) <= 16
            and not re.search(r"[\u4e00-\u9fff].*-[A-Za-z]\b", raw_query)
        ):
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
                normalized_display = f"{primary_name} {display_name}".translate(fullwidth_ascii_map)
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
                if market not in stock_like_markets:
                    score -= 60
                if not any(token in cleaned_query.lower() for token in ["wr", "权证", "窝轮", "牛熊", "认购", "认沽"]):
                    if re.search(r"(wr\b|权证|窝轮|牛熊|认购|认沽|ＷＲ|轮证)", f"{primary_name} {display_name}", flags=re.IGNORECASE):
                        score -= 40
                if re.search(r"(?i)-w\b", normalized_cleaned_query):
                    if re.search(r"(?i)-wr\b", normalized_display):
                        score -= 120
                    elif re.search(r"(?i)-w\b", normalized_display):
                        score += 28
                if query_has_chinese:
                    if any(hint in market_hint_text for hint in ["港股", "hk", "h股", "恒生"]):
                        if market == "31":
                            score += 20
                    elif any(hint in market_hint_text for hint in ["美股", "us", "纳斯达克", "纽交所", "adr"]):
                        if market in {"41", "103"}:
                            score += 20
                    else:
                        if market in {"11", "12", "31"}:
                            score += 12
                        elif market in {"41", "103"}:
                            score -= 18
                if market in {"11", "12", "31", "41", "71", "73", "103"}:
                    score += 6

                candidates.append({
                    "code": code,
                    "name": display_name or primary_name or code,
                    "score": score,
                })

        if not candidates:
            return results

        deduped_candidates: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            code = str(candidate.get("code") or "").strip()
            if not code:
                continue
            prev = deduped_candidates.get(code)
            if prev is None or float(candidate.get("score", 0)) > float(prev.get("score", 0)):
                deduped_candidates[code] = candidate

        ranked_candidates = sorted(
            deduped_candidates.values(),
            key=lambda item: float(item.get("score", 0)),
            reverse=True,
        )

        stock_code = ""
        stock_name = ""
        content = ""
        for candidate in ranked_candidates[:8]:
            candidate_code = str(candidate.get("code") or "").strip()
            candidate_name = str(candidate.get("name") or candidate_code).strip()
            if not candidate_code:
                continue

            query_codes = [candidate_code]
            if candidate_code.startswith("hk"):
                query_codes.append(f"rt_{candidate_code}")

            for c in query_codes:
                hq_url = f"http://hq.sinajs.cn/list={c}"
                hq_resp = requests.get(hq_url, headers=headers, timeout=6)
                if hq_resp.status_code != 200:
                    continue
                val_match = re.search(r'="(.*?)"', hq_resp.text)
                if not val_match or not val_match.group(1).strip():
                    continue
                candidate_content = val_match.group(1).strip()
                candidate_vals = candidate_content.split(",")
                if not _quote_has_usable_price(c, candidate_vals):
                    continue
                content = candidate_content
                stock_code = c
                stock_name = candidate_name
                break

            if content:
                break

        if not content or not stock_code:
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
# 搜索工具：直接搜索引擎结果页 + 正文抓取
# ------------------------------------------------------------
def perform_web_search(query: str, max_results: int = 8) -> List[dict]:
    """
    Web search via SearXNG JSON API.
    """
    query = str(query or "").strip()
    if not query:
        return []

    q_lower = query.lower()
    prefer_fresh = any(k in q_lower for k in ["现在", "当前", "实时", "最新", "today", "now", "今日", "刚刚", "近况"])
    is_exchange_query = _looks_like_exchange_rate_query(query)
    defer_searxng_return = (prefer_fresh or _is_reason_search_query(query)) and not is_exchange_query
    query_variants = _build_search_query_variants(query, prefer_fresh=prefer_fresh)
    best_searxng_results: List[dict] = []
    best_searxng_score = float("-inf")

    print(f"🔍 [Search] Trying provider=searxng query={query}")
    for query_variant in query_variants:
        try:
            effective_query = query_variant
            if prefer_fresh:
                now_stamp = datetime.now().strftime("%Y-%m-%d")
                effective_query = f"{query_variant} {now_stamp} 最新"

            provider_rows = _search_with_searxng(effective_query, max_results=max_results * 2, prefer_fresh=prefer_fresh)
            picked = _post_process_search_results(provider_rows, query_variant, max_results=max_results)
            quality = _score_search_results_quality(picked, query_variant)
            if picked and quality > best_searxng_score:
                best_searxng_results = picked
                best_searxng_score = quality
            if picked and quality >= 24.0 and (not defer_searxng_return or quality >= 90.0):
                print(f"✅ [Search] provider=searxng query={query_variant} results={len(picked)} score={quality:.1f}")
                return picked
        except Exception as e:
            print(f"⚠️ [Search] provider=searxng query={query_variant} failed: {e}")

    if best_searxng_results:
        if is_exchange_query:
            print(f"✅ [Search] exchange query using SearXNG-only results. best_score={best_searxng_score:.1f}")
            return best_searxng_results
        print(f"⚠️ [Search] SearXNG results weak, trying HTML fallback. best_score={best_searxng_score:.1f}")

    best_fallback_results: List[dict] = []
    best_fallback_score = float("-inf")
    for query_variant in query_variants:
        try:
            fallback_rows = _perform_web_search_scraping(query_variant, max_results=max_results * 2)
            picked = _post_process_search_results(fallback_rows, query_variant, max_results=max_results)
            quality = _score_search_results_quality(picked, query_variant)
            if picked and quality > best_fallback_score:
                best_fallback_results = picked
                best_fallback_score = quality
            if picked and quality >= 12.0:
                print(f"✅ [Search] provider=html-fallback query={query_variant} results={len(picked)} score={quality:.1f}")
                return picked
        except Exception as e:
            print(f"⚠️ [Search] provider=html-fallback query={query_variant} failed: {e}")

    if best_fallback_results and best_fallback_score >= best_searxng_score:
        return best_fallback_results
    if best_searxng_results:
        return best_searxng_results

    print("⚠️ [Search] No usable results from SearXNG or HTML fallback.")
    return []


def _direct_search_headers(referer: str) -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
        "Cache-Control": "no-cache",
    }


def _resolve_search_result_link(link: str, *, headers: Optional[Dict[str, str]] = None) -> str:
    if not link or not str(link).strip():
        return ""
    candidate = str(link).strip()
    if not candidate.startswith(("http://", "https://")):
        return candidate

    import requests

    try:
        resp = requests.get(candidate, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=6, allow_redirects=True)
        final_url = str(resp.url or candidate).strip()
        body = resp.text or ""
        if final_url == candidate and body:
            js_redirect = re.search(r'window\.location\.replace\("([^"]+)"\)', body, flags=re.IGNORECASE)
            meta_redirect = re.search(r"URL='([^']+)'", body, flags=re.IGNORECASE)
            redirected = (js_redirect.group(1) if js_redirect else "") or (meta_redirect.group(1) if meta_redirect else "")
            if redirected.startswith(("http://", "https://")):
                final_url = redirected
        return final_url or candidate
    except Exception:
        return candidate


def _search_with_bing_html(query: str, max_results: int) -> List[dict]:
    import requests
    from bs4 import BeautifulSoup

    results: List[dict] = []
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&setlang=zh-hans&count={max(max_results, 10)}"
    resp = requests.get(url, headers=_direct_search_headers("https://cn.bing.com/"), timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ [Search/Bing HTML] Error {resp.status_code}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select("#b_results > li.b_algo, #b_results > li.b_ans"):
        if len(results) >= max_results:
            break
        classes = item.get("class", []) or []
        if any(cls in {"b_ad", "b_mop"} for cls in classes):
            continue

        title_tag = item.select_one("h2 > a") or item.select_one("a")
        if not title_tag:
            continue

        title = title_tag.get_text(" ", strip=True)
        link = str(title_tag.get("href") or "").strip()
        if not title or not link or link.startswith(("/", "javascript:")):
            continue

        snippet = ""
        for selector in (".b_caption p", ".b_lineclamp2", ".b_lineclamp3", ".news_dt", ".b_paractl"):
            s_tag = item.select_one(selector)
            if s_tag:
                snippet = s_tag.get_text(" ", strip=True)
                if snippet:
                    break
        if not snippet:
            snippet = item.get_text(" ", strip=True)[:180]

        results.append({
            "title": title,
            "link": link,
            "snippet": snippet,
            "provider": "bing-html",
        })

    return results


def _search_with_sogou_html(query: str, max_results: int) -> List[dict]:
    import requests
    from bs4 import BeautifulSoup

    results: List[dict] = []
    headers = _direct_search_headers("https://www.sogou.com/")
    url = f"https://www.sogou.com/web?query={urllib.parse.quote(query)}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ [Search/Sogou HTML] Error {resp.status_code}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    for item in soup.select(".results > div, .vrwrap, .rb"):
        if len(results) >= max_results:
            break

        title_tag = item.select_one("h3 a") or item.select_one("a")
        if not title_tag:
            continue

        title = title_tag.get_text(" ", strip=True)
        link = str(title_tag.get("href") or "").strip()
        if not title or not link:
            continue

        if link.startswith("/link?"):
            link = _resolve_search_result_link(f"https://www.sogou.com{link}", headers=headers)
        elif link.startswith("https://www.sogou.com/link?") or link.startswith("http://www.sogou.com/link?"):
            link = _resolve_search_result_link(link, headers=headers)
        elif link.startswith("/"):
            continue

        snippet_tag = item.select_one(".text-layout") or item.select_one(".ft") or item.select_one("p")
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else item.get_text(" ", strip=True)[:180]

        results.append({
            "title": title,
            "link": link,
            "snippet": snippet,
            "provider": "sogou-html",
        })

    return results


def _perform_web_search_scraping(query: str, max_results: int) -> List[dict]:
    """Direct HTML search against public search engines."""
    providers = (
        [
            ("sogou-html", _search_with_sogou_html),
            ("bing-html", _search_with_bing_html),
        ]
        if re.search(r"[\u4e00-\u9fff]", query or "")
        else [
            ("bing-html", _search_with_bing_html),
            ("sogou-html", _search_with_sogou_html),
        ]
    )

    best_results: List[dict] = []
    best_score = float("-inf")
    for provider_name, provider_fn in providers:
        try:
            rows = provider_fn(query, max_results=max_results)
            picked = _post_process_search_results(rows, query, max_results=max_results)
            quality = _score_search_results_quality(picked, query)
            if picked and quality > best_score:
                best_results = picked
                best_score = quality
            if picked:
                print(f"✅ [Search] provider={provider_name} raw={len(rows)} picked={len(picked)} score={quality:.1f}")
        except Exception as e:
            print(f"⚠️ [Search] provider={provider_name} failed: {e}")

    return best_results


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
    r"你是什么(模型|大模型|llm)",
    r"你用的是什么(模型|大模型|llm)",
    r"你属于什么(模型|大模型|llm)",
    r"你(用的|属于)?什么(模型|大模型|llm)",
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

    def _normalize_persisted_sources_payload(sources: Any) -> List[Any]:
        if not isinstance(sources, list):
            return []
        normalized_sources: List[Any] = []
        for item in sources:
            if isinstance(item, (dict, list, str, int, float, bool)) or item is None:
                normalized_sources.append(item)
                continue
            try:
                normalized_sources.append(json.loads(json.dumps(item, ensure_ascii=False, default=str)))
            except Exception:
                normalized_sources.append(str(item))
        return normalized_sources

    async def _persist_turn_for_feedback(
            func_type: str,
            user_message: str,
            assistant_message: str,
            sources: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, int]]:
        if user_id == "anonymous":
            return None
        saved = await _save_history_turn_async(
            user_id,
            session_id,
            func_type,
            user_message,
            assistant_message,
        )
        if not isinstance(saved, dict):
            return None

        history_ids: Dict[str, int] = {}
        user_history_id = saved.get("user_id")
        assistant_history_id = saved.get("assistant_id")
        if user_history_id not in (None, ""):
            history_ids["user"] = int(user_history_id)
        if assistant_history_id not in (None, ""):
            assistant_history_id = int(assistant_history_id)
            history_ids["assistant"] = assistant_history_id
            normalized_sources = _normalize_persisted_sources_payload(sources)
            if normalized_sources:
                try:
                    await asyncio.to_thread(
                        _append_meta_history_event,
                        user_id,
                        session_id,
                        "message_sources",
                        {
                            "assistant_history_id": assistant_history_id,
                            "func_type": func_type,
                            "sources": normalized_sources,
                        },
                    )
                except Exception as e:
                    print(f"Message source history save failed: {e}")
        return history_ids or None

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

            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        "identity",
                        message,
                        IDENTITY_FIXED_REPLY,
                    )
                except Exception as e:
                    print(f"Identity reply history save failed: {e}")

            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
    if user_id != "anonymous":
        _schedule_background_io(
            _maybe_append_context_event_async(
                user_id=user_id,
                session_id=session_id,
                mode=mode,
                model_id=model_id,
                model_backend=model_backend,
                context_content=context_content,
                personalization=personalization,
            ),
            "context_event",
        )
        _schedule_background_io(
            _maybe_store_long_term_hint_async(user_id, message),
            "long_term_hint",
        )

    print(
        f"🚀 [Chat] New Request: User={user_id}, Session={session_id}, Mode={mode}, Backend={model_backend}, Files={len(requested_source_files)}"
    )

    shared_context_cache: Dict[str, Dict[str, str]] = {}
    shared_context_refresh_flags: Dict[str, bool] = {}

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
            compaction_snapshot = _collect_context_compaction_snapshot(
                user_id=user_id,
                session_id=session_id,
                mode=normalized_mode,
            )
            compaction_payload = compaction_snapshot.get("payload")
            session_state = _build_compaction_context_block(compaction_payload)
            shared_context_refresh_flags[cache_key] = bool(compaction_snapshot.get("needs_refresh"))
        except Exception:
            compaction_payload = None
            session_state = ""
            shared_context_refresh_flags[cache_key] = False

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
        normalized_mode = (target_mode or mode or "general").strip().lower() or "general"
        cache_key = f"{normalized_mode}:{history_limit}"
        bundle = await asyncio.to_thread(_get_shared_context, target_mode, history_limit)
        if shared_context_refresh_flags.pop(cache_key, False):
            _schedule_background_io(
                _refresh_context_compaction_async(
                    user_id=user_id,
                    session_id=session_id,
                    mode=normalized_mode,
                    model_backend=model_backend,
                ),
                "context_compaction",
            )
        return bundle

    def _augment_shared_context_with_feedback(
            shared_ctx: Dict[str, str],
            target_mode: Optional[str],
            user_message: Optional[str] = None,
    ) -> Dict[str, str]:
        feedback_context = _build_feedback_learning_context(
            user_id=user_id,
            session_id=session_id,
            mode=_normalize_mode(target_mode or mode),
            query=user_message if user_message is not None else message,
        )
        if not feedback_context:
            return shared_ctx
        merged = dict(shared_ctx or {})
        existing_summary = str(merged.get("summary_context") or "").strip()
        merged["summary_context"] = (
            f"{feedback_context}\n\n{existing_summary}" if existing_summary else feedback_context
        )
        return merged

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
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, active_mode, user_message=message)
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

            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        func_type,
                        message,
                        full_reply,
                    )
                except Exception as e:
                    print(f" History save failed: {e}")

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": return_mode, "end": True}, ensure_ascii=False) + "\n"
        except Exception as e:
            print(f" [Chat Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"Error: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": return_mode, "end": True}, ensure_ascii=False) + "\n"

    async def webpage_response_generator(page_urls: List[str]):
        yield json.dumps({"t": "m", "sid": session_id}, ensure_ascii=False) + "\n"

        full_reply = ""
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)
        try:
            urls_text = "、".join(page_urls[:3])
            yield json.dumps({"t": "c", "v": f"> 正在抓取网页：{urls_text}\n\n"}, ensure_ascii=False) + "\n"

            scrape_result = await asyncio.to_thread(scrape_urls_for_chat, page_urls)
            pages = list(scrape_result.get("pages") or [])
            scrape_errors = list(scrape_result.get("errors") or [])

            if _is_cancelled():
                return

            if pages:
                source_rows = []
                for page in pages:
                    final_url = str(page.get("final_url") or page.get("url") or "").strip()
                    source_rows.append({
                        "type": "web",
                        "title": str(page.get("title") or final_url or "网页内容").strip(),
                        "link": final_url,
                        "snippet": str(page.get("snippet") or "").strip(),
                        "source": str(page.get("source") or "").strip(),
                    })
                if source_rows:
                    yield json.dumps({"t": "m", "sid": session_id, "src": source_rows}, ensure_ascii=False) + "\n"

            if not pages:
                failure_parts = ["未能抓取到可用网页内容。"]
                if scrape_errors:
                    top_error = scrape_errors[0]
                    failure_parts.append(
                        f"失败链接：{top_error.get('url', '')}，原因：{top_error.get('error', '未知错误')}"
                    )
                failure_text = "\n".join(part for part in failure_parts if part).strip()
                full_reply = failure_text
                yield json.dumps({"t": "c", "v": failure_text}, ensure_ascii=False) + "\n"
            else:
                yield json.dumps(
                    {"t": "c", "v": f"> 已抓取 {len(pages)} 个网页，正在整理内容...\n\n"},
                    ensure_ascii=False,
                ) + "\n"

                shared_ctx = await _get_shared_context_async("general", history_limit=FAST_CHAT_HISTORY_LIMIT)
                shared_ctx = _augment_shared_context_with_feedback(shared_ctx, "general", user_message=message)
                webpage_blocks = []
                for index, page in enumerate(pages, start=1):
                    title = str(page.get("title") or page.get("final_url") or f"网页{index}").strip()
                    final_url = str(page.get("final_url") or page.get("url") or "").strip()
                    source_name = str(page.get("source") or "").strip()
                    content = _truncate_context(str(page.get("content") or "").strip(), max_len=MAX_CONTEXT_CHARS)
                    meta_line = f"来源域名: {source_name}\n" if source_name else ""
                    webpage_blocks.append(
                        f"[{index}] 标题: {title}\nURL: {final_url}\n{meta_line}正文:\n{content}"
                    )

                error_lines = []
                for item in scrape_errors[:2]:
                    error_url = str(item.get("url") or "").strip()
                    error_msg = str(item.get("error") or "").strip()
                    if error_url or error_msg:
                        error_lines.append(f"- {error_url}: {error_msg}".strip())
                partial_error_block = ""
                if error_lines:
                    partial_error_block = "以下链接未成功抓取，仅供你参考，不应编造成已读取内容：\n" + "\n".join(error_lines)

                base_prompt = (
                    "你是企业网页内容助手。"
                    "用户在通用问答中提供了网页链接，系统已经抓取并提取了网页正文。"
                    "回答时只能基于下方“网页抓取内容”和已有会话上下文，不要编造页面中不存在的事实。\n"
                    "回答规则：\n"
                    "1) 若用户只发链接或需求不明确，优先给出简洁摘要；\n"
                    "2) 若用户提出明确任务（总结、提炼、翻译、抽取、改写、分析），直接完成；\n"
                    "3) 如果抓取内容不足以支持结论，明确说明“信息不足”；\n"
                    "4) 引用网页事实时尽量标注来源编号，如[1][2]；\n\n"
                    f"用户原始请求：\n{message}\n\n"
                    f"{partial_error_block}\n\n"
                    "网页抓取内容：\n"
                    + "\n\n".join(webpage_blocks)
                ).strip()
                system_prompt = _merge_system_prompt(
                    "You are an enterprise assistant. Use the fetched webpage content as primary evidence.",
                    personalization_system_prompt,
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

            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        "web",
                        message,
                        full_reply,
                    )
                except Exception as e:
                    print(f"Webpage reply history save failed: {e}")

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "general", "end": True}, ensure_ascii=False) + "\n"
        except Exception as e:
            print(f" [Webpage Mode Error]: {e}")
            yield json.dumps({"t": "c", "v": f"Error: {str(e)}"}, ensure_ascii=False) + "\n"
            yield json.dumps({"t": "m", "sid": session_id, "mode": "general", "end": True}, ensure_ascii=False) + "\n"

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

    def _is_exchange_query(text: str) -> bool:
        return _looks_like_exchange_rate_query(text)

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
        q = re.sub(r"^(就|那就|那|请|帮我|麻烦|先|再|给我)\s*", "", q)
        q = re.sub(r"\s*(一下|一下子|吧|呢|呀|啊)$", "", q)
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
        if _is_exchange_query(text):
            return "exchange"
        if _is_stock_query(text):
            return "stock"
        if _is_gold_query(text):
            return "gold"
        if _is_profile_query(text):
            return "profile"
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
        persisted_sources: List[Dict[str, Any]] = []
        push_chunk, flush_chunk = _make_text_buffer(immediate=True)

        try:
            shared_ctx = await _get_shared_context_async("search", history_limit=FAST_CHAT_HISTORY_LIMIT)
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, "search", user_message=message)
            history_text = shared_ctx.get("history_text", "")
            now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            contextual_user_query = _build_contextual_search_query(message, history_text)

            intent_probe = f"{message} {contextual_user_query}".strip()
            is_realtime_query = _is_realtime_sensitive_query(message) or (
                _is_explicit_followup_query(message) and _is_realtime_sensitive_query(intent_probe)
            )
            length_req = _extract_length_requirement(message)
            raw_search_query = str(message or "").strip()
            rewrite_seed = message if _is_profile_query(message) else (contextual_user_query or message)
            search_domain = (
                _detect_query_domain(message)
                or _detect_query_domain(rewrite_seed)
            )
            if search_domain:
                search_query = _rewrite_search_query_for_searxng(rewrite_seed, history_text)
            elif _is_explicit_followup_query(message):
                search_query = _build_general_search_query(contextual_user_query or raw_search_query)
            else:
                search_query = _build_general_search_query(raw_search_query or str(contextual_user_query or "").strip())
            search_domain = search_domain or _detect_query_domain(search_query)
            scrape_page_limit = SEARCH_SCRAPE_PAGE_LIMIT_REALTIME if (is_realtime_query or search_domain == "weather") else SEARCH_SCRAPE_PAGE_LIMIT

            if search_domain in {"weather", "stock", "gold", "exchange"}:
                tool_query = contextual_user_query or message
                if search_domain == "weather":
                    progress_text = "> 正在查询天气预报：{query}\n\n"
                elif search_domain == "stock":
                    progress_text = "> 正在查询实时股价：{query}\n\n"
                elif search_domain == "gold":
                    progress_text = "> 正在查询实时金价：{query}\n\n"
                else:
                    progress_text = "> 正在查询实时汇率：{query}\n\n"
                yield json.dumps({"t": "c", "v": progress_text.format(query=tool_query)}, ensure_ascii=False) + "\n"

                if search_domain == "weather":
                    market_sources = await asyncio.to_thread(tool_get_weather, tool_query)
                elif search_domain == "stock":
                    market_sources = await asyncio.to_thread(tool_get_stock, tool_query)
                elif search_domain == "gold":
                    market_sources = await asyncio.to_thread(tool_get_gold_price, tool_query)
                else:
                    market_sources = await asyncio.to_thread(tool_get_exchange_rate, tool_query)

                if _is_cancelled():
                    return

                if market_sources:
                    persisted_sources = list(market_sources)
                    yield json.dumps({"t": "m", "sid": session_id, "src": market_sources}, ensure_ascii=False) + "\n"
                    if search_domain in {"weather", "exchange"}:
                        direct_market_answer = _build_direct_exchange_answer(tool_query, market_sources)
                        if search_domain == "weather":
                            direct_market_answer = _build_direct_weather_answer(tool_query, market_sources)
                    else:
                        direct_market_answer = _build_direct_market_tool_answer(market_sources[0], domain=search_domain)
                    if direct_market_answer:
                        full_reply_clean = direct_market_answer
                        for part in _split_text(full_reply_clean):
                            if _is_cancelled():
                                return
                            yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                            await asyncio.sleep(0)
                        if _is_cancelled():
                            return
                        history_ids = None
                        if user_id != "anonymous":
                            try:
                                history_ids = await _persist_turn_for_feedback(
                                    "search",
                                    message,
                                    full_reply_clean,
                                    sources=persisted_sources,
                                )
                            except Exception as e:
                                print(f"[Search] history save failed: {e}")
                        if _is_cancelled():
                            return
                        if history_ids:
                            yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
                        yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"
                        return

            yield json.dumps({"t": "c", "v": f"> 正在搜索：{search_query}\n\n"}, ensure_ascii=False) + "\n"

            raw_results = await asyncio.to_thread(perform_web_search, search_query)
            search_results = _post_process_search_results(raw_results, search_query, max_results=6)
            fallback_fetch_candidates = _build_domain_fallback_fetch_items(search_query, search_domain)

            if _is_cancelled():
                return

            if not search_results and not fallback_fetch_candidates:
                no_result_text = "未检索到可靠结果。请换个关键词再试。"
                full_reply_clean = no_result_text
                yield json.dumps({"t": "c", "v": no_result_text}, ensure_ascii=False) + "\n"
            else:
                fetch_candidates = _pick_search_fetch_items(
                    search_results,
                    search_query,
                    limit=scrape_page_limit,
                    domain=search_domain,
                )
                if fallback_fetch_candidates:
                    merged_candidates = list(fallback_fetch_candidates) + list(fetch_candidates)
                    deduped_candidates = []
                    seen_candidate_links = set()
                    for item in merged_candidates:
                        link = str(item.get("link") or "").strip()
                        link_key = _canonicalize_link(link)
                        if not link_key or link_key in seen_candidate_links:
                            continue
                        seen_candidate_links.add(link_key)
                        deduped_candidates.append(item)
                        if len(deduped_candidates) >= scrape_page_limit:
                            break
                    fetch_candidates = deduped_candidates
                fetch_urls = [
                    str(item.get("link") or "").strip()
                    for item in fetch_candidates
                    if str(item.get("link") or "").strip()
                ]
                fetched_pages: List[Dict[str, Any]] = []
                scrape_errors: List[Dict[str, str]] = []

                if not SCRAPLING_AVAILABLE or not scrape_urls_for_chat:
                    raise RuntimeError(f"Scrapling unavailable: {SCRAPLING_IMPORT_ERROR}")

                if fetch_urls:
                    yield json.dumps(
                        {
                            "t": "c",
                            "v": f"> 已获取 {len(search_results)} 条搜索结果，正在抓取前 {len(fetch_urls)} 个网页正文...\n\n",
                        },
                        ensure_ascii=False,
                    ) + "\n"
                    scrape_result = await asyncio.to_thread(scrape_urls_for_chat, fetch_urls)
                    fetched_pages = list(scrape_result.get("pages") or [])
                    scrape_errors = list(scrape_result.get("errors") or [])
                    filtered_pages: List[Dict[str, Any]] = []
                    for page in fetched_pages:
                        final_url = str(page.get("final_url") or page.get("url") or "").strip()
                        if not _is_valid_search_result_link(final_url):
                            continue
                        filtered_pages.append(page)
                    fetched_pages = filtered_pages

                if _is_cancelled():
                    return

                search_lookup: Dict[str, Dict[str, Any]] = {}
                for item in search_results:
                    link_key = _canonicalize_link(str(item.get("link") or ""))
                    if link_key and link_key not in search_lookup:
                        search_lookup[link_key] = item

                search_sources = []
                if fetched_pages:
                    for page in fetched_pages[:scrape_page_limit]:
                        final_url = str(page.get("final_url") or page.get("url") or "").strip()
                        lookup = search_lookup.get(_canonicalize_link(final_url)) or search_lookup.get(
                            _canonicalize_link(str(page.get("url") or ""))
                        ) or {}
                        search_sources.append({
                            "type": "web",
                            "title": str(page.get("title") or lookup.get("title") or final_url or "网页内容").strip(),
                            "link": final_url,
                            "snippet": str(page.get("snippet") or lookup.get("snippet") or "").strip(),
                            "date": str(lookup.get("date") or "").strip(),
                            "source": str(page.get("source") or lookup.get("source") or "").strip(),
                        })
                else:
                    for item in search_results[:5]:
                        search_sources.append({
                            "type": "web",
                            "title": str(item.get("title") or "").strip(),
                            "link": str(item.get("link") or "").strip(),
                            "snippet": str(item.get("snippet") or "").strip(),
                            "date": str(item.get("date") or "").strip(),
                            "source": str(item.get("source") or "").strip(),
                        })
                if search_sources:
                    persisted_sources = list(search_sources)
                    yield json.dumps({"t": "m", "sid": session_id, "src": search_sources}, ensure_ascii=False) + "\n"

                if not fetched_pages:
                    failure_parts = ["搜索结果已获取，但未能抓取到可用网页正文。"]
                    if scrape_errors:
                        top_error = scrape_errors[0]
                        failure_parts.append(
                            f"失败链接：{top_error.get('url', '')}，原因：{top_error.get('error', '未知错误')}"
                        )
                    failure_text = "\n".join(part for part in failure_parts if part).strip()
                    full_reply_clean = failure_text
                    yield json.dumps({"t": "c", "v": failure_text}, ensure_ascii=False) + "\n"
                else:
                    if search_domain == "weather":
                        weather_direct_answer = _build_direct_weather_answer(search_query, fetched_pages)
                        if weather_direct_answer:
                            full_reply_clean = weather_direct_answer
                            for part in _split_text(full_reply_clean):
                                if _is_cancelled():
                                    return
                                yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                                await asyncio.sleep(0)
                            if _is_cancelled():
                                return
                            history_ids = None
                            if user_id != "anonymous":
                                try:
                                    history_ids = await _persist_turn_for_feedback(
                                        "search",
                                        message,
                                        full_reply_clean,
                                        sources=persisted_sources,
                                    )
                                except Exception as e:
                                    print(f"[Search] history save failed: {e}")
                            if _is_cancelled():
                                return
                            if history_ids:
                                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
                            yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"
                            return
                    elif search_domain == "exchange":
                        exchange_direct_answer = _build_direct_exchange_answer(search_query, fetched_pages)
                        if exchange_direct_answer:
                            full_reply_clean = exchange_direct_answer
                            for part in _split_text(full_reply_clean):
                                if _is_cancelled():
                                    return
                                yield json.dumps({"t": "c", "v": part}, ensure_ascii=False) + "\n"
                                await asyncio.sleep(0)
                            if _is_cancelled():
                                return
                            history_ids = None
                            if user_id != "anonymous":
                                try:
                                    history_ids = await _persist_turn_for_feedback(
                                        "search",
                                        message,
                                        full_reply_clean,
                                        sources=persisted_sources,
                                    )
                                except Exception as e:
                                    print(f"[Search] history save failed: {e}")
                            if _is_cancelled():
                                return
                            if history_ids:
                                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
                            yield json.dumps({"t": "m", "sid": session_id, "mode": "search", "end": True}, ensure_ascii=False) + "\n"
                            return

                    page_context_limit = max(700, min(SEARCH_CONTEXT_PAGE_MAX_CHARS, MAX_CONTEXT_CHARS // max(1, len(fetched_pages))))
                    fetched_context_lines = []
                    for i, page in enumerate(fetched_pages[:scrape_page_limit], start=1):
                        final_url = str(page.get("final_url") or page.get("url") or "").strip()
                        lookup = search_lookup.get(_canonicalize_link(final_url)) or search_lookup.get(
                            _canonicalize_link(str(page.get("url") or ""))
                        ) or {}
                        title = str(page.get("title") or lookup.get("title") or final_url or f"结果{i}").strip()
                        source_name = str(page.get("source") or lookup.get("source") or "").strip()
                        search_snippet = str(lookup.get("snippet") or "").strip()
                        content = _truncate_context(str(page.get("content") or "").strip(), max_len=page_context_limit)
                        meta_lines = []
                        if source_name:
                            meta_lines.append(f"来源域名: {source_name}")
                        if search_snippet:
                            meta_lines.append(f"搜索摘要: {search_snippet}")
                        meta_block = "\n".join(meta_lines)
                        fetched_context_lines.append(
                            (
                                f"[{i}] 标题: {title}\n"
                                f"URL: {final_url}\n"
                                f"{meta_block + chr(10) if meta_block else ''}"
                                f"正文:\n{content}"
                            ).strip()
                        )

                    scrape_error_lines = []
                    for item in scrape_errors[:2]:
                        error_url = str(item.get("url") or "").strip()
                        error_msg = str(item.get("error") or "").strip()
                        if error_url or error_msg:
                            scrape_error_lines.append(f"- {error_url}: {error_msg}".strip())

                    auxiliary_search_lines = []
                    if search_domain != "profile":
                        for i, item in enumerate(search_results[:5], start=1):
                            title = str(item.get("title") or "").strip()
                            snippet = str(item.get("snippet") or "").strip()
                            link = str(item.get("link") or "").strip()
                            auxiliary_search_lines.append(
                                f"候选结果{i}: {title}\n链接: {link}\n摘要: {snippet}"
                            )

                    if auxiliary_search_lines:
                        search_context = (
                            "搜索结果摘要（辅助参考，不视为已验证事实）：\n"
                            + "\n\n".join(auxiliary_search_lines)
                            + "\n\n已抓取网页正文（主要证据）：\n"
                            + "\n\n".join(fetched_context_lines)
                        ).strip()
                    else:
                        search_context = (
                            "已抓取网页正文（主要证据）：\n" + "\n\n".join(fetched_context_lines)
                        ).strip()
                    if scrape_error_lines:
                        search_context += (
                            "\n\n以下候选链接抓取失败，不应当作已读取证据：\n"
                            + "\n".join(scrape_error_lines)
                        )

                    length_rule_text = _build_length_rule_text(length_req)
                    domain_specific_rules = ""
                    if search_domain == "weather":
                        domain_specific_rules = (
                            "天气类问题的补充规则：\n"
                            "6) 如果证据中存在具体数值，必须直接给出天气现象、当前温度、最高/最低气温、风向风力、更新时间；\n"
                            "7) 如果用户问的是明天/后天，不能拿今天的数据替代，只有证据里明确出现对应日期时才能回答；\n"
                            "8) 不要只说“可以访问以下网站获取”，而是直接输出提取到的天气数据；\n"
                            "9) 多来源数值略有差异时，优先中国天气网/中央气象台，其次天气网/2345，并简要说明来源。\n"
                        )
                    elif search_domain == "exchange":
                        domain_specific_rules = (
                            "汇率类问题的补充规则：\n"
                            "6) 如果证据中存在具体汇率，必须直接给出数值和更新时间；\n"
                            "7) 如果页面给的是反向币对，例如 JPY/CNY，而用户问的是 CNY/JPY，需要先换算再回答；\n"
                            "8) 历史教程、经验贴、操作说明不能当作当前汇率证据；\n"
                            "9) 优先使用 XE、Wise、Sina 外汇、Exchange-Rates 等实时汇率页面。\n"
                        )
                    elif search_domain == "profile":
                        domain_specific_rules = (
                            "介绍/简介类问题的补充规则：\n"
                            "6) 优先概括实体是什么、成立时间、总部地点、创始人/主体、主营业务等基础信息；\n"
                            "7) 不要把招聘、待遇、测评、购买建议、论坛讨论当作主体介绍；\n"
                            "8) 如果抓到的是百科或官网页面，优先引用这些来源；\n"
                            "9) 用户只是要求介绍时，不要擅自扩展到股价、招聘、面试、产品推荐等无关内容。\n"
                        )
                    response_prompt = (
                        "你是企业联网检索助手。"
                        "系统已经先通过搜索引擎检索，再抓取了部分结果页的网页正文。"
                        "回答时必须优先依据“已抓取网页正文”，搜索摘要只能作为辅助线索，不能当作已验证事实。\n"
                        "回答规则：\n"
                        "1) 先给结论，再给2-5条关键依据；\n"
                        "2) 每条关键事实后标注来源编号，如[1][3]；\n"
                        "3) 若证据不足或互相冲突，明确写“信息不足/信息冲突”；\n"
                        "4) 不要编造来源，不要输出与问题无关内容；\n"
                        "5) 必须完整满足用户原问题里的硬性要求（字数、格式、语气、输出结构）。\n"
                        f"{domain_specific_rules}"
                        f"当前本地时间: {now_local}\n"
                        f"字数要求: {length_rule_text or '未指定'}\n"
                        f"时效性要求: {'高（优先最新信息）' if is_realtime_query else '普通'}\n\n"
                        f"用户问题:\n{message}\n\n"
                        f"证据材料:\n{search_context}\n\n"
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
                                f"证据材料:\n{search_context}\n\n"
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

            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        "search",
                        message,
                        full_reply_clean,
                        sources=persisted_sources,
                    )
                except Exception as e:
                    print(f"[Search] history save failed: {e}")

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, "database", user_message=message)
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
            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        "database",
                        message,
                        full_reply,
                        sources=db_sources,
                    )
                except Exception as e:
                    print(f"History save failed: {e}")

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, "audit", user_message=message)
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
            history_ids = None
            if user_id != "anonymous":
                history_ids = await _persist_turn_for_feedback(
                    "audit",
                    message,
                    full_reply,
                )

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, "rag", user_message=message)
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

            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        "rag",
                        message,
                        full_reply,
                        sources=srcs,
                    )
                except Exception as e:
                    print(f"[RAG] history save failed: {e}")

            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
            shared_ctx = _augment_shared_context_with_feedback(shared_ctx, mode, user_message=message)
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
            history_ids = None
            if user_id != "anonymous":
                try:
                    history_ids = await _persist_turn_for_feedback(
                        final_intent,
                        message,
                        full_reply_clean,
                        sources=sources,
                    )
                except Exception as e:
                    print(f"History save failed: {e}")

            # 图阶段回退处理
            if _is_cancelled():
                return
            if history_ids:
                yield json.dumps({"t": "m", "sid": session_id, "history_ids": history_ids}, ensure_ascii=False) + "\n"
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
    message_urls = (
        extract_supported_urls(message)
        if auto_routing_enabled and SCRAPLING_AVAILABLE and extract_supported_urls
        else []
    )

    is_doc_query = _is_doc_query(message) if (auto_routing_enabled and not rag_route_blocked) else False
    is_db_query = False
    if auto_routing_enabled and (not db_route_blocked) and _is_db_question_by_tables:
        try:
            is_db_query = _is_db_question_by_tables(message)[0]
        except Exception:
            is_db_query = False

    if auto_routing_enabled and (not db_route_blocked) and not is_db_query:
        is_db_query = _looks_like_db_request(message)

    if auto_routing_enabled and message_urls:
        return _stream(webpage_response_generator(message_urls))

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
def get_session_messages_api(
    session_id: str,
    user_id: str,
    limit: Optional[int] = Query(default=None),
    before_id: Optional[int] = Query(default=None),
    include_context: bool = Query(default=False),
):
    if limit is not None or before_id is not None or include_context:
        return get_history_page(
            user_id,
            session_id,
            limit=limit or 40,
            before_id=before_id,
            include_context=include_context,
        )
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


@router.patch("/history/{session_id}/pin")
def pin_session_api(session_id: str, user_id: str, req: SessionPinRequest):
    success = set_session_pinned(user_id, session_id, req.pinned)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update session pin state")
    return {"status": "ok", "message": "Session pin updated", "pinned": bool(req.pinned)}


@router.get("/chat/feedback/{session_id}")
def get_chat_feedback_api(session_id: str, ctx: Dict[str, Any] = Depends(require_active_user)):
    safe_session_id = str(session_id or "").strip()
    if not safe_session_id:
        raise HTTPException(status_code=422, detail="session_id 不能为空")
    return {
        "status": "ok",
        "session_id": safe_session_id,
        "feedback": _get_session_feedback_map(str(ctx["user_id"]), safe_session_id),
    }


@router.post("/chat/feedback")
def submit_chat_feedback_api(req: ChatFeedbackRequest, ctx: Dict[str, Any] = Depends(require_active_user)):
    safe_session_id = str(req.session_id or "").strip()
    if not safe_session_id:
        raise HTTPException(status_code=422, detail="session_id 不能为空")

    requested_feedback = str(req.feedback_type or "").strip()
    normalized_feedback = _normalize_feedback_type(req.feedback_type)
    if requested_feedback and normalized_feedback is None:
        raise HTTPException(status_code=422, detail="feedback_type 仅支持 up / down")

    user_id = str(ctx["user_id"])
    resolved = _resolve_feedback_history_context(
        user_id=user_id,
        session_id=safe_session_id,
        history_id=req.history_id,
        assistant_message=req.assistant_message,
        user_message=req.user_message,
    )
    safe_message_key = _build_feedback_message_key(
        history_id=resolved.get("history_id"),
        message_key=req.message_key,
        session_id=resolved.get("session_id") or safe_session_id,
        assistant_message=resolved.get("assistant_message") or req.assistant_message,
    )

    if normalized_feedback is None:
        deleted = _clear_chat_feedback(user_id, safe_message_key)
        return {
            "status": "ok",
            "cleared": True,
            "deleted": deleted,
            "message_key": safe_message_key,
            "history_id": resolved.get("history_id"),
        }

    saved = _save_chat_feedback(
        user_id=user_id,
        session_id=str(resolved.get("session_id") or safe_session_id),
        history_id=resolved.get("history_id"),
        message_key=safe_message_key,
        feedback_type=normalized_feedback,
        user_message=resolved.get("user_message") or req.user_message,
        assistant_message=resolved.get("assistant_message") or req.assistant_message,
        mode=req.mode or resolved.get("mode"),
        model_backend=req.model_backend,
        model_id=req.model_id,
        metadata=req.metadata,
    )

    return {
        "status": "ok",
        "cleared": False,
        "feedback": {
            "message_key": saved.get("message_key") or safe_message_key,
            "feedback_type": saved.get("feedback_type") or normalized_feedback,
            "feedback_score": saved.get("feedback_score"),
            "history_id": saved.get("history_id") or resolved.get("history_id"),
            "session_id": saved.get("session_id") or str(resolved.get("session_id") or safe_session_id),
            "updated_at": saved.get("updated_at"),
        },
    }

