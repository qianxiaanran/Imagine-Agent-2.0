from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app_settings import PRESENTON_API_KEY, PRESENTON_BASE_URL
from admin_utils import ROLE_ADMIN, require_role
from deepseek_llm import ask_llm
from runtime_storage import (
    PRESENTATION_TEMPLATE_REGISTRY_FILE,
    ensure_runtime_layout,
    migrate_legacy_runtime_files,
)
from task_registry import build_task_result_link, get_task as get_registered_task, upsert_task

router = APIRouter(prefix="/api/presentation", tags=["Presentation"])
ensure_runtime_layout()
migrate_legacy_runtime_files()

DEFAULT_PRESENTON_BASE_URL = PRESENTON_BASE_URL.strip()
DEFAULT_PRESENTON_API_KEY = PRESENTON_API_KEY.strip()

LOCAL_GENERATE_PATH = os.getenv("PRESENTON_LOCAL_PATH", "/api/v1/ppt/presentation/generate").strip()
CLOUD_SYNC_PATH = os.getenv("PRESENTON_SYNC_PATH", "/api/v1/ppt/presentation/generate/sync").strip()
CLOUD_ASYNC_PATH = os.getenv("PRESENTON_ASYNC_PATH", "/api/v1/ppt/presentation/generate/async").strip()
STATUS_PATH_TEMPLATE = os.getenv("PRESENTON_STATUS_PATH_TEMPLATE", "/api/v1/ppt/presentation/status/{task_id}").strip()
TEMPLATE_GROUP_PATH = os.getenv("PRESENTON_TEMPLATE_GROUP_PATH", "/api/template?group={template_id}").strip() or "/api/template?group={template_id}"
CREATE_PRESENTATION_PATH = os.getenv("PRESENTON_CREATE_PRESENTATION_PATH", "/api/v1/ppt/presentation/create").strip() or "/api/v1/ppt/presentation/create"
PREPARE_PRESENTATION_PATH = os.getenv("PRESENTON_PREPARE_PRESENTATION_PATH", "/api/v1/ppt/presentation/prepare").strip() or "/api/v1/ppt/presentation/prepare"
STREAM_PRESENTATION_PATH_TEMPLATE = os.getenv("PRESENTON_STREAM_PRESENTATION_PATH_TEMPLATE", "/api/v1/ppt/presentation/stream/{presentation_id}").strip() or "/api/v1/ppt/presentation/stream/{presentation_id}"
EXPORT_PRESENTATION_PATH = os.getenv("PRESENTON_EXPORT_PRESENTATION_PATH", "/api/v1/ppt/presentation/export").strip() or "/api/v1/ppt/presentation/export"
TEMPLATE_LIST_PATHS = [
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH", "/api/v1/ppt/template/all").strip() or "/api/v1/ppt/template/all",
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH_V3", "/api/v3/standard-template").strip() or "/api/v3/standard-template",
    os.getenv("PRESENTON_TEMPLATE_LIST_PATH_TM", "/api/v1/ppt/template-management/summary").strip()
    or "/api/v1/ppt/template-management/summary",
]
TEMPLATE_DETAIL_PATHS = [
    os.getenv("PRESENTON_TEMPLATE_DETAIL_PATH", "/api/v1/ppt/template/{template_id}").strip() or "/api/v1/ppt/template/{template_id}",
    os.getenv("PRESENTON_TEMPLATE_DETAIL_PATH_V3", "/api/v3/standard-template/{template_id}").strip() or "/api/v3/standard-template/{template_id}",
]
TEMPLATE_REGISTRY_FILE = PRESENTATION_TEMPLATE_REGISTRY_FILE

REQUEST_TIMEOUT_SEC = float(os.getenv("PRESENTON_REQUEST_TIMEOUT_SEC", "180"))
POLL_TIMEOUT_SEC = float(os.getenv("PRESENTON_POLL_TIMEOUT_SEC", "900"))
POLL_INTERVAL_SEC = float(os.getenv("PRESENTON_POLL_INTERVAL_SEC", "2"))
OUTLINE_LLM_TIMEOUT_SEC = float(os.getenv("PRESENTON_OUTLINE_LLM_TIMEOUT_SEC", "45"))
OUTLINE_LLM_MAX_WORKERS = max(1, int(os.getenv("PRESENTON_OUTLINE_LLM_MAX_WORKERS", "4")))
INVALID_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
PRESENTON_PROXY_PREFIX = "/api/presentation/presenton/proxy"
PRESENTON_USER_CONFIG_PATH = os.getenv("PRESENTON_USER_CONFIG_PATH", "/api/user-config").strip() or "/api/user-config"
PPT_RUNTIME_MODEL = os.getenv("PRESENTON_PPT_RUNTIME_MODEL", "qwen3:1.7b").strip() or "qwen3:1.7b"
PPT_RESTORE_MODEL = os.getenv("PRESENTON_PPT_RESTORE_MODEL", "qwen2.5-coder:latest").strip() or "qwen2.5-coder:latest"
PPT_IMAGE_PROVIDER_DISABLED = os.getenv("PRESENTON_PPT_IMAGE_PROVIDER_DISABLED", "none").strip() or "none"
PPT_IMAGE_PROVIDER_RESTORE = os.getenv("PRESENTON_PPT_IMAGE_PROVIDER_RESTORE", "").strip()
PPT_KEEP_FAST_RUNTIME = os.getenv("PRESENTON_PPT_KEEP_FAST_RUNTIME", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_FORCE_IMAGE_PROVIDER_OVERRIDE = os.getenv("PRESENTON_PPT_FORCE_IMAGE_PROVIDER_OVERRIDE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_MODEL_KEEP_ALIVE = os.getenv("PRESENTON_PPT_MODEL_KEEP_ALIVE", "1h").strip() or "1h"
OLLAMA_CONTROL_URL = (
    os.getenv("PRESENTON_OLLAMA_CONTROL_URL")
    or os.getenv("OLLAMA_API_BASE")
    or "http://127.0.0.1:11434"
).strip().rstrip("/")
OLLAMA_CONTROL_TIMEOUT_SEC = float(os.getenv("PRESENTON_OLLAMA_CONTROL_TIMEOUT_SEC", "8"))
PPT_RUNTIME_CONFIG_TIMEOUT_SEC = float(os.getenv("PRESENTON_RUNTIME_CONFIG_TIMEOUT_SEC", "20"))
PPT_RUNTIME_SWITCH_STRICT = os.getenv("PRESENTON_RUNTIME_SWITCH_STRICT", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_ENFORCE_SINGLE_OLLAMA_MODEL = os.getenv("PRESENTON_ENFORCE_SINGLE_OLLAMA_MODEL", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PPT_TASK_STALE_SEC = float(os.getenv("PRESENTON_PPT_TASK_STALE_SEC", "7200"))
ORDERED_TEMPLATE_COOLDOWN_SEC = float(os.getenv("PRESENTON_ORDERED_TEMPLATE_COOLDOWN_SEC", "1800"))
TERMINAL_TASK_STATUSES = {"completed", "done", "success", "succeeded", "failed", "error", "cancelled", "canceled"}
ORDERED_UNSAFE_TEMPLATE_PREFIXES = tuple(
    item.strip().lower()
    for item in str(os.getenv("PRESENTON_ORDERED_UNSAFE_TEMPLATE_PREFIXES", "neo-")).split(",")
    if item.strip()
)
ORDERED_UNSAFE_TEMPLATES = {
    item.strip().lower()
    for item in str(os.getenv("PRESENTON_ORDERED_UNSAFE_TEMPLATES", "")).split(",")
    if item.strip()
}
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
PROXY_CACHE_REQUEST_HEADERS = {
    "if-match",
    "if-none-match",
    "if-modified-since",
    "if-unmodified-since",
    "if-range",
}
PROXY_CACHE_RESPONSE_HEADERS = {
    "etag",
    "last-modified",
    "expires",
}
PROXY_REWRITE_CONTENT_TYPES = ("text/html", "text/css", "application/javascript", "text/javascript")
LOCAL_HOST_CANDIDATES = {"127.0.0.1", "localhost", "0.0.0.0", "host.docker.internal"}
ROOT_RELATIVE_REF_RE = re.compile(
    rf"([\"'])/(?!/|{re.escape(PRESENTON_PROXY_PREFIX.lstrip('/'))})(?=[A-Za-z0-9._~%?-])([^\"']*)"
)
CSS_ROOT_RELATIVE_URL_RE = re.compile(
    rf"url\((?P<quote>[\"']?)/(?!/|{re.escape(PRESENTON_PROXY_PREFIX.lstrip('/'))})(?P<path>[^)\"']*)(?P=quote)\)"
)

_PRESENTON_SESSION = requests.Session()
_PRESENTON_SESSION.mount("http://", HTTPAdapter(pool_connections=32, pool_maxsize=128, max_retries=0))
_PRESENTON_SESSION.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=128, max_retries=0))
_OUTLINE_LLM_EXECUTOR = ThreadPoolExecutor(max_workers=OUTLINE_LLM_MAX_WORKERS, thread_name_prefix="ppt-outline")
_MODEL_RUNTIME_LOCK = threading.Lock()
_ACTIVE_PPT_TASKS: Dict[str, float] = {}
_ORDERED_PPT_TASK_LOCK = threading.Lock()
_ORDERED_PPT_TASKS: Dict[str, Dict[str, Any]] = {}
_ORDERED_TEMPLATE_COOLDOWN_LOCK = threading.Lock()
_ORDERED_TEMPLATE_COOLDOWNS: Dict[str, Dict[str, Any]] = {}
_TEMPLATE_REGISTRY_LOCK = threading.Lock()
_TEMPLATE_GROUP_CACHE_LOCK = threading.Lock()
_TEMPLATE_GROUP_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_IMAGE_PROVIDER: Optional[str] = None
logger = logging.getLogger(__name__)

LEGACY_TEMPLATE_ALIASES: Dict[str, str] = {
    "corporate": "standard",
    "minimal": "modern",
}
BUILTIN_TEMPLATE_CATALOG: List[Dict[str, Any]] = [
    {"template_id": "neo-general", "name": "Neo 通用", "description": "新版通用风格，适合综合汇报、日常演示与常规业务表达。", "source": "builtin"},
    {"template_id": "neo-standard", "name": "Neo 标准", "description": "新版标准风格，结构更规整，适合正式汇报与章节型内容。", "source": "builtin"},
    {"template_id": "neo-modern", "name": "Neo 现代", "description": "新版现代风格，视觉更鲜明，适合方案展示与重点表达。", "source": "builtin"},
    {"template_id": "neo-swift", "name": "Neo 迅捷", "description": "新版迅捷风格，节奏更明快，适合路演展示与信息快读。", "source": "builtin"},
    {"template_id": "general", "name": "经典通用", "description": "经典通用模板，适合常规商务汇报与多场景演示。", "source": "builtin"},
    {"template_id": "modern", "name": "经典现代", "description": "经典现代模板，适合产品介绍、品牌展示与视觉化表达。", "source": "builtin"},
    {"template_id": "standard", "name": "经典标准", "description": "经典标准模板，适合制度宣讲、项目汇报与正式文稿。", "source": "builtin"},
    {"template_id": "swift", "name": "经典迅捷", "description": "经典迅捷模板，适合数据概览、快节奏汇报与重点传达。", "source": "builtin"},
]
BUILTIN_TEMPLATE_CATALOG_LOOKUP: Dict[str, Dict[str, Any]] = {
    str(item.get("template_id") or "").strip(): dict(item) for item in BUILTIN_TEMPLATE_CATALOG
}
BUILTIN_TEMPLATE_CATALOG_ORDER: Dict[str, int] = {
    str(item.get("template_id") or "").strip(): index for index, item in enumerate(BUILTIN_TEMPLATE_CATALOG)
}
PRESENTON_UI_TRANSLATIONS: List[Tuple[str, str]] = [
    ("Loading custom templates...", "正在加载自定义模板..."),
    ("Custom templates you create will appear here.", "你创建的自定义模板会显示在这里。"),
    ("Create new template", "创建新模板"),
    ("No custom templates yet.", "暂无自定义模板。"),
    ("My Custom Templates", "我的自定义模板"),
    ("Inbuilt Templates", "内置模板"),
    ("All Templates", "全部模板"),
    ("Create Template", "创建模板"),
    ("No preview", "暂无预览"),
    ("Custom Template", "自定义模板"),
    ("User-created template", "用户创建的模板"),
    ("Templates", "模板"),
    ("Dashboard", "工作台"),
    ("Settings", "设置"),
]
PRESENTON_TEMPLATE_PREVIEW_TEXT_MAP: Dict[str, str] = {
    "Create Template": "创建模板",
    "Templates": "模板",
    "Dashboard": "工作台",
    "Settings": "设置",
    "All Templates": "全部模板",
    "Inbuilt Templates": "内置模板",
    "My Custom Templates": "我的自定义模板",
    "Create new template": "创建新模板",
    "Loading custom templates...": "正在加载自定义模板...",
    "No custom templates yet.": "暂无自定义模板。",
    "Custom templates you create will appear here.": "你创建的自定义模板会显示在这里。",
    "No preview": "暂无预览",
    "Custom Template": "自定义模板",
    "User-created template": "用户创建的模板",
    "Neo General": "Neo 通用",
    "Neo Standard": "Neo 标准",
    "Neo Modern": "Neo 现代",
    "Neo Swift": "Neo 迅捷",
    "New general purpose layouts for common presentation elements": "适用于常见演示元素的通用版式模板",
    "New standard purpose layouts for common presentation elements": "适用于常见演示元素的标准版式模板",
    "New modern purpose layouts for common presentation elements": "适用于常见演示元素的现代版式模板",
    "New swift purpose layouts for common presentation elements": "适用于常见演示元素的迅捷版式模板",
}
PRESENTON_TEMPLATE_PREVIEW_REGEX_RULES: List[Tuple[str, str]] = [
    (r"(\d+)\s+layouts across\s+(\d+)\s+templates", r"$1 个版式，覆盖 $2 个模板"),
    (r"^Slide\s+(\d+)$", r"第 $1 页"),
]


class PresentonGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=4, max_length=12000, description="PPT 生成提示词")
    n_slides: int = Field(default=10, ge=3, le=40, description="页数")
    language: str = Field(default="Chinese", max_length=64)
    template: str = Field(default="general", max_length=64)
    export_as: str = Field(default="pptx", max_length=16)
    tone: str = Field(default="professional", max_length=32)
    verbosity: str = Field(default="standard", max_length=32)
    image_type: Optional[str] = Field(default=None, max_length=32)
    content_generation: Optional[str] = Field(default=None, max_length=32)
    markdown_emphasis: Optional[str] = Field(default=None, max_length=32)
    web_search: Optional[bool] = None
    slides_markdown: Optional[List[str]] = None
    slides_layout: Optional[List[str]] = None
    include_table_of_contents: Optional[bool] = None
    include_title_slide: Optional[bool] = None
    allow_access_to_user_info: Optional[bool] = None
    trigger_webhook: Optional[bool] = None
    files: Optional[List[str]] = None
    provider: Literal["auto", "local", "cloud_sync", "cloud_async"] = "auto"
    base_url: Optional[str] = None
    user_id: Optional[str] = None


class PresentonOutlineRequest(BaseModel):
    input_mode: Literal["topic", "document", "longText"] = "topic"
    content_focus: str = Field(default="work_report", max_length=64)
    analysis_framework: Optional[str] = Field(default=None, max_length=64)
    analysis_input: str = Field(default="", max_length=14000)
    document_name: Optional[str] = Field(default=None, max_length=256)
    n_slides: int = Field(default=8, ge=3, le=40)
    language: str = Field(default="Chinese", max_length=64)
    require_metrics: bool = True
    include_images: bool = False
    model_backend: Literal["local", "cloud"] = "local"


class PresentonTemplateImportRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=120)
    alias: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=300)


def _normalize_requested_image_type(image_type: Optional[str]) -> str:
    value = str(image_type or "").strip().lower()
    if value in {"", "off", "false", "disabled", "0", "no"}:
        return ""
    return value


def _images_enabled(req: PresentonGenerateRequest) -> bool:
    resolved_image_type = _normalize_requested_image_type(req.image_type)
    if resolved_image_type == "none":
        return False
    if resolved_image_type:
        return True
    return bool(getattr(req, "include_images", False))


def _prefer_no_image(req: PresentonGenerateRequest) -> bool:
    return not _images_enabled(req)


OUTLINE_CONTENT_FOCUS_CONFIG: Dict[str, Dict[str, Any]] = {
    "work_report": {
        "label": "工作汇报",
        "sections": ["封面", "汇报摘要", "目录", "背景与目标", "阶段进展", "核心成果", "问题与挑战", "原因复盘", "改进动作", "下一步计划", "资源诉求", "总结"],
        "prompt_lines": [
            "内容导向：工作汇报，适合周报、月报、项目总结、阶段复盘类 PPT。",
            "结构重点：围绕目标背景、阶段进展、关键成果、存在问题、复盘原因和下一步计划展开。",
            "表达方式：结论前置，结果清晰，适合管理层和团队同步。",
            "页面组织：优先使用结论式标题，每页围绕一个核心信息展开，再补充事实、数据和行动要点。",
        ],
    },
    "proposal": {
        "label": "方案提案",
        "sections": ["封面", "提案摘要", "目录", "现状痛点", "目标与原则", "方案总览", "关键模块", "实施路径", "资源与分工", "收益评估", "风险保障", "结论"],
        "prompt_lines": [
            "内容导向：方案提案，适合立项汇报、解决方案、项目建议书类 PPT。",
            "结构重点：讲清现状痛点、目标原则、方案设计、实施路径、资源需求、收益与风险。",
            "表达方式：强调可执行性和决策价值，让听众能快速判断是否推进。",
            "页面组织：优先使用问题-方案-收益的表达顺序，让每页都能服务于决策判断。",
        ],
    },
    "analysis": {
        "label": "分析解读",
        "sections": ["封面", "核心结论", "目录", "研究背景", "现状与趋势", "关键数据", "原因拆解", "对比分析", "洞察发现", "策略建议", "风险提示", "总结"],
        "prompt_lines": [
            "内容导向：分析解读，适合行业研究、专题分析、经营复盘类 PPT。",
            "结构重点：基于事实和数据得出洞察，再形成结论、判断与建议。",
            "表达方式：强调逻辑链和证据链，避免只有结论没有支撑。",
            "页面组织：优先使用结论-证据-影响的表达顺序，让听众能快速跟上分析逻辑。",
        ],
    },
    "training": {
        "label": "培训讲解",
        "sections": ["封面", "培训目标", "目录", "概念导入", "知识拆解", "方法步骤", "案例演示", "常见问题", "注意事项", "实操建议", "练习复盘", "总结"],
        "prompt_lines": [
            "内容导向：培训讲解，适合课程分享、制度宣讲、方法培训类 PPT。",
            "结构重点：概念解释、知识拆解、步骤演示、案例说明、注意事项和练习复盘。",
            "表达方式：更注重可理解性和可学习性，内容要循序渐进。",
            "页面组织：优先使用概念-步骤-示例-提醒的表达顺序，帮助听众边看边学。",
        ],
    },
    "product_pitch": {
        "label": "产品路演",
        "sections": ["封面", "一句话价值", "目录", "用户场景", "痛点机会", "产品方案", "核心亮点", "竞争优势", "商业价值", "客户案例", "实施计划", "结语"],
        "prompt_lines": [
            "内容导向：产品路演，适合产品介绍、业务宣讲、商业展示类 PPT。",
            "结构重点：说明场景与痛点、产品价值、核心亮点、竞争优势、商业价值和落地计划。",
            "表达方式：强调价值主张和说服力，让听众快速理解卖点。",
            "页面组织：优先使用场景-价值-亮点-证明的表达顺序，让页面更有路演说服力。",
        ],
    },
}


def _normalize_base_url(base_url: Optional[str]) -> str:
    raw = (base_url or DEFAULT_PRESENTON_BASE_URL or "").strip()
    if not raw:
        raise HTTPException(status_code=500, detail="Presenton base URL is not configured")
    return raw.rstrip("/")


def _build_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if DEFAULT_PRESENTON_API_KEY:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"
    return headers


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_model_to_dict(req: PresentonGenerateRequest) -> Dict[str, Any]:
    if hasattr(req, "model_dump"):
        return req.model_dump(exclude_none=True)
    return req.dict(exclude_none=True)


def _extract_prompt_preview(req: PresentonGenerateRequest) -> str:
    prompt = str(req.prompt or "").strip()
    if prompt:
        return prompt[:280]
    slides = req.slides_markdown or []
    if not slides:
        return "PPT 生成任务"
    joined = " ".join(str(item or "").strip() for item in slides[:2]).strip()
    return joined[:280] or "PPT 生成任务"


def _build_presenton_task_title(req: PresentonGenerateRequest) -> str:
    preview = _extract_prompt_preview(req)
    if not preview:
        return "PPT 生成任务"
    first_line = preview.splitlines()[0].strip()
    if len(first_line) > 56:
        first_line = f"{first_line[:56].rstrip()}..."
    return f"PPT 生成 · {first_line}"


def _sync_presenton_task_registry(
    task_id: str,
    *,
    req: Optional[PresentonGenerateRequest] = None,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error_message: Optional[str] = None,
    download_url: Optional[str] = None,
    edit_url: Optional[str] = None,
    provider: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing = get_registered_task(task_id) or {}
    request_payload = dict(existing.get("source_payload") or {})
    if req is not None:
        request_payload = _request_model_to_dict(req)

    normalized_provider = str(
        provider
        or existing.get("detail", {}).get("provider")
        or request_payload.get("provider")
        or "cloud_async"
    ).strip()
    prompt_preview = _extract_prompt_preview(req) if req is not None else str(
        existing.get("detail", {}).get("prompt_preview")
        or request_payload.get("prompt", "")
    )[:280]
    detail = dict(existing.get("detail") or {})
    detail.update(
        {
            "provider": normalized_provider,
            "template": request_payload.get("template"),
            "slide_count": request_payload.get("n_slides"),
            "language": request_payload.get("language"),
            "prompt_preview": prompt_preview,
            "message": message if message is not None else detail.get("message"),
            "download_url": download_url if download_url is not None else detail.get("download_url"),
            "edit_url": edit_url if edit_url is not None else detail.get("edit_url"),
            "raw": raw if raw is not None else detail.get("raw"),
        }
    )
    if detail.get("download_url"):
        detail["has_download"] = True

    status_value = status or existing.get("status") or "queued"
    progress_value = progress if progress is not None else existing.get("progress", 0)
    return upsert_task(
        {
            "task_id": task_id,
            "task_type": "ppt",
            "user_id": str(request_payload.get("user_id") or existing.get("user_id") or "anonymous").strip()
            or "anonymous",
            "title": _build_presenton_task_title(req) if req is not None else existing.get("title") or "PPT 生成任务",
            "status": status_value,
            "progress": progress_value,
            "started_at": existing.get("started_at") or _utc_now_iso(),
            "error_message": error_message if error_message is not None else existing.get("error_message"),
            "result_link": build_task_result_link(task_id),
            "retry_supported": True,
            "detail": detail,
            "source_payload": request_payload,
        }
    )

def _template_retry_candidates(raw_template: Any) -> List[str]:
    value = str(raw_template or "").strip()
    if not value:
        return ["general"]
    candidates: List[str] = [value]
    lowered = value.lower()
    alias_target = LEGACY_TEMPLATE_ALIASES.get(lowered)
    if alias_target:
        candidates.append(alias_target)
    if lowered in {"auto", "default"}:
        candidates.append("general")
    if lowered.startswith("custom-") and len(value) > len("custom-"):
        candidates.append(value[len("custom-"):])
    if lowered.startswith("neo-") and len(value) > len("neo-"):
        candidates.append(value[len("neo-"):])
    unique: List[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique or ["general"]


def _supports_ordered_pipeline_template(raw_template: Any, prefer_no_image: bool = False) -> bool:
    template_id = str(raw_template or "").strip().lower()
    if not template_id:
        return True
    if template_id.startswith("custom-"):
        return False
    if template_id in ORDERED_UNSAFE_TEMPLATES:
        return False
    if prefer_no_image and template_id.startswith("neo-"):
        return True
    return not any(template_id.startswith(prefix) for prefix in ORDERED_UNSAFE_TEMPLATE_PREFIXES)


def _ordered_pipeline_skip_reason(req: PresentonGenerateRequest) -> Optional[str]:
    if not isinstance(req.slides_markdown, list) or not req.slides_markdown:
        return "missing_slide_markdown"
    prefer_no_image = _prefer_no_image(req)
    if not _supports_ordered_pipeline_template(req.template, prefer_no_image=prefer_no_image):
        return "compatibility_policy"
    cooldown = _get_ordered_template_cooldown(req.template, prefer_no_image)
    if cooldown:
        reason = str(cooldown.get("reason") or "recent_failure").strip() or "recent_failure"
        return f"recent_failure:{reason}"
    return None


def _upsert_ordered_task(task_id: str, **changes: Any) -> Dict[str, Any]:
    now_iso = _utc_now_iso()
    with _ORDERED_PPT_TASK_LOCK:
        current = dict(_ORDERED_PPT_TASKS.get(task_id) or {})
        if not current:
            current = {
                "success": True,
                "provider": "ordered_async",
                "task_id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "",
                "error": None,
                "download_url": None,
                "edit_url": None,
                "download_url_raw": None,
                "edit_url_raw": None,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        if "message" in changes:
            changes["message"] = _translate_progress_message(changes.get("message"))
        current.update(changes)
        current["message"] = _translate_progress_message(current.get("message"))
        current["updated_at"] = now_iso
        _ORDERED_PPT_TASKS[task_id] = current
        return dict(current)


def _get_ordered_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _ORDERED_PPT_TASK_LOCK:
        current = _ORDERED_PPT_TASKS.get(task_id)
        return dict(current) if current else None


def _normalize_model_name(model_name: Optional[str]) -> str:
    value = str(model_name or "").strip().lower()
    if not value:
        return ""
    return value if ":" in value else f"{value}:latest"


def _is_same_model(model_a: Optional[str], model_b: Optional[str]) -> bool:
    a = _normalize_model_name(model_a)
    b = _normalize_model_name(model_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.removesuffix(":latest") == b.removesuffix(":latest")


def _runtime_config_timeout() -> float:
    upper = REQUEST_TIMEOUT_SEC if REQUEST_TIMEOUT_SEC > 0 else 20.0
    preferred = PPT_RUNTIME_CONFIG_TIMEOUT_SEC if PPT_RUNTIME_CONFIG_TIMEOUT_SEC > 0 else 20.0
    return max(3.0, min(upper, preferred))


def _handle_runtime_switch_error(step: str, exc: Exception) -> None:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    logger.warning("%s: %s", step, detail)
    if PPT_RUNTIME_SWITCH_STRICT:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=f"{step}: {detail}") from exc


def _ollama_request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not OLLAMA_CONTROL_URL:
        raise HTTPException(status_code=500, detail="OLLAMA control URL is not configured")
    endpoint = f"{OLLAMA_CONTROL_URL}{path}"
    try:
        response = _PRESENTON_SESSION.request(
            method=method,
            url=endpoint,
            json=payload,
            timeout=OLLAMA_CONTROL_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Ollama control request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except Exception:
        data = {"raw_text": raw_text[:1200]}

    if response.status_code >= 400:
        detail = data.get("error") or data.get("message") or data.get("detail") or data.get("raw_text")
        raise HTTPException(status_code=502, detail=f"Ollama control error ({response.status_code}): {detail}")
    return data


def _list_loaded_ollama_models() -> List[str]:
    data = _ollama_request_json("GET", "/api/ps")
    models = data.get("models")
    if not isinstance(models, list):
        return []
    result: List[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        candidate = item.get("name") or item.get("model")
        if candidate:
            result.append(str(candidate))
    return result


def _set_presenton_ollama_model(base_url: str, model_name: str, image_provider: Optional[str] = None) -> None:
    runtime_timeout = _runtime_config_timeout()
    payload = {
        "LLM": "ollama",
        "OLLAMA_MODEL": model_name,
    }
    if image_provider is not None:
        payload["IMAGE_PROVIDER"] = str(image_provider).strip()
    try:
        _request_json(
            "POST",
            f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
            {"Content-Type": "application/json"},
            payload=payload,
            timeout=runtime_timeout,
        )
    except HTTPException as exc:
        # Some deployments may not accept IMAGE_PROVIDER in user config update payload.
        if image_provider is not None:
            logger.warning("Failed to set IMAGE_PROVIDER in user config, fallback to model-only update: %s", exc.detail)
            payload.pop("IMAGE_PROVIDER", None)
            _request_json(
                "POST",
                f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
                {"Content-Type": "application/json"},
                payload=payload,
                timeout=runtime_timeout,
            )
            return
        raise


def _read_presenton_user_config(base_url: str) -> Dict[str, Any]:
    try:
        data = _request_json(
            "GET",
            f"{base_url}{PRESENTON_USER_CONFIG_PATH}",
            {"Content-Type": "application/json"},
            payload=None,
            timeout=_runtime_config_timeout(),
        )
    except HTTPException:
        return {}
    return data if isinstance(data, dict) else {}


def _unload_ollama_model(model_name: str) -> None:
    _ollama_request_json(
        "POST",
        "/api/generate",
        payload={
            "model": model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        },
    )


def _warmup_ollama_model(model_name: str) -> None:
    _ollama_request_json(
        "POST",
        "/api/generate",
        payload={
            "model": model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": PPT_MODEL_KEEP_ALIVE,
        },
    )


def _ensure_only_ollama_model(target_model: str) -> None:
    # Keep only one mounted model in memory to avoid cross-model contention during PPT generation.
    loaded_before = _list_loaded_ollama_models()
    for model_name in loaded_before:
        if _is_same_model(model_name, target_model):
            continue
        try:
            _unload_ollama_model(model_name)
        except HTTPException as exc:
            logger.warning("Failed to unload model %s: %s", model_name, exc.detail)

    loaded_mid = _list_loaded_ollama_models()
    if not any(_is_same_model(item, target_model) for item in loaded_mid):
        _warmup_ollama_model(target_model)

    loaded_after = _list_loaded_ollama_models()
    for model_name in loaded_after:
        if _is_same_model(model_name, target_model):
            continue
        try:
            _unload_ollama_model(model_name)
        except HTTPException as exc:
            logger.warning("Second-pass unload failed for model %s: %s", model_name, exc.detail)


def _enforce_single_ollama_model_if_needed(target_model: str, stage: str) -> None:
    if not PPT_ENFORCE_SINGLE_OLLAMA_MODEL:
        return
    try:
        _ensure_only_ollama_model(target_model)
    except Exception as exc:
        _handle_runtime_switch_error(f"Failed to enforce single Ollama model during {stage}", exc)


def _activate_ppt_runtime(base_url: str) -> None:
    global _LAST_IMAGE_PROVIDER
    if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE and _LAST_IMAGE_PROVIDER is None:
        try:
            current = _read_presenton_user_config(base_url)
            current_provider = str(current.get("IMAGE_PROVIDER") or "").strip()
            if current_provider:
                _LAST_IMAGE_PROVIDER = current_provider
        except Exception as exc:
            _handle_runtime_switch_error("Failed to read Presenton user config before runtime activation", exc)

    target_image_provider = PPT_IMAGE_PROVIDER_DISABLED if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE else None
    current_config = _read_presenton_user_config(base_url)
    current_model = str(current_config.get("OLLAMA_MODEL") or "").strip()
    current_provider = str(current_config.get("IMAGE_PROVIDER") or "").strip()
    provider_matches = (
        target_image_provider is None
        or current_provider == str(target_image_provider).strip()
    )
    if _is_same_model(current_model, PPT_RUNTIME_MODEL) and provider_matches:
        _enforce_single_ollama_model_if_needed(PPT_RUNTIME_MODEL, "runtime activation")
        return
    try:
        _set_presenton_ollama_model(base_url, PPT_RUNTIME_MODEL, image_provider=target_image_provider)
    except Exception as exc:
        _handle_runtime_switch_error("Failed to activate PPT runtime model", exc)
        return
    _enforce_single_ollama_model_if_needed(PPT_RUNTIME_MODEL, "runtime activation")


def _restore_default_runtime(base_url: str) -> None:
    if PPT_KEEP_FAST_RUNTIME:
        logger.info("Skip restoring default Presenton runtime; keeping fast model resident: %s", PPT_RUNTIME_MODEL)
        _enforce_single_ollama_model_if_needed(PPT_RUNTIME_MODEL, "runtime keepalive")
        return
    restore_provider = None
    if PPT_FORCE_IMAGE_PROVIDER_OVERRIDE:
        restore_provider = _LAST_IMAGE_PROVIDER or PPT_IMAGE_PROVIDER_RESTORE
    try:
        _set_presenton_ollama_model(base_url, PPT_RESTORE_MODEL, image_provider=restore_provider if restore_provider else None)
    except Exception as exc:
        _handle_runtime_switch_error("Failed to restore default runtime model", exc)
        return
    _enforce_single_ollama_model_if_needed(PPT_RESTORE_MODEL, "runtime restore")


def _purge_stale_tasks_locked(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    stale_ids = [task_id for task_id, ts in _ACTIVE_PPT_TASKS.items() if (now - ts) > PPT_TASK_STALE_SEC]
    for task_id in stale_ids:
        _ACTIVE_PPT_TASKS.pop(task_id, None)


def _purge_stale_ordered_tasks(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    with _ORDERED_PPT_TASK_LOCK:
        stale_ids: List[str] = []
        for task_id, payload in _ORDERED_PPT_TASKS.items():
            updated_at = str(payload.get("updated_at") or payload.get("created_at") or "").strip()
            try:
                updated_ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                updated_ts = now
            if (now - updated_ts) > PPT_TASK_STALE_SEC:
                stale_ids.append(task_id)
        for task_id in stale_ids:
            _ORDERED_PPT_TASKS.pop(task_id, None)


def _ordered_template_cooldown_key(raw_template: Any, prefer_no_image: bool) -> str:
    template_id = str(raw_template or "").strip().lower() or "general"
    return f"{template_id}::no_image={1 if prefer_no_image else 0}"


def _purge_stale_ordered_template_cooldowns(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    with _ORDERED_TEMPLATE_COOLDOWN_LOCK:
        stale_keys = [
            key
            for key, payload in _ORDERED_TEMPLATE_COOLDOWNS.items()
            if now >= float(payload.get("expires_at") or 0)
        ]
        for key in stale_keys:
            _ORDERED_TEMPLATE_COOLDOWNS.pop(key, None)


def _get_ordered_template_cooldown(raw_template: Any, prefer_no_image: bool) -> Optional[Dict[str, Any]]:
    _purge_stale_ordered_template_cooldowns()
    key = _ordered_template_cooldown_key(raw_template, prefer_no_image)
    with _ORDERED_TEMPLATE_COOLDOWN_LOCK:
        payload = _ORDERED_TEMPLATE_COOLDOWNS.get(key)
        return dict(payload) if payload else None


def _mark_ordered_template_cooldown(raw_template: Any, prefer_no_image: bool, reason: str) -> None:
    clean_reason = str(reason or "").strip()
    if ORDERED_TEMPLATE_COOLDOWN_SEC <= 0:
        return
    key = _ordered_template_cooldown_key(raw_template, prefer_no_image)
    expires_at = time.time() + ORDERED_TEMPLATE_COOLDOWN_SEC
    with _ORDERED_TEMPLATE_COOLDOWN_LOCK:
        _ORDERED_TEMPLATE_COOLDOWNS[key] = {
            "template": str(raw_template or "").strip() or "general",
            "prefer_no_image": prefer_no_image,
            "reason": clean_reason,
            "expires_at": expires_at,
        }


def _clear_ordered_template_cooldown(raw_template: Any, prefer_no_image: bool) -> None:
    key = _ordered_template_cooldown_key(raw_template, prefer_no_image)
    with _ORDERED_TEMPLATE_COOLDOWN_LOCK:
        _ORDERED_TEMPLATE_COOLDOWNS.pop(key, None)


def _join_url(base_url: str, path_or_url: Optional[str]) -> Optional[str]:
    if path_or_url is None:
        return None
    value = str(path_or_url).strip()
    if not value:
        return None
    safe_value = INVALID_PERCENT_RE.sub("%25", value)
    if safe_value.startswith("http://") or safe_value.startswith("https://"):
        return requests.utils.requote_uri(safe_value)
    if safe_value.startswith("/"):
        return requests.utils.requote_uri(f"{base_url}{safe_value}")
    return requests.utils.requote_uri(f"{base_url}/{safe_value}")


def _extract_task_id(payload: Dict[str, Any]) -> Optional[str]:
    candidates = [
        payload.get("task_id"),
        payload.get("request_id"),
        payload.get("id"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("task_id"), data.get("request_id"), data.get("id")])
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _extract_urls(payload: Dict[str, Any], base_url: str) -> Tuple[Optional[str], Optional[str]]:
    data = payload.get("data")
    nested: Dict[str, Any] = data if isinstance(data, dict) else {}

    download_candidates = [
        payload.get("download_url"),
        payload.get("file_url"),
        payload.get("url"),
        payload.get("path"),
        payload.get("pptx_url"),
        nested.get("download_url"),
        nested.get("file_url"),
        nested.get("url"),
        nested.get("path"),
        nested.get("pptx_url"),
    ]
    edit_candidates = [
        payload.get("edit_url"),
        payload.get("edit_path"),
        nested.get("edit_url"),
        nested.get("edit_path"),
    ]

    download_url = next((_join_url(base_url, item) for item in download_candidates if _join_url(base_url, item)), None)
    edit_url = next((_join_url(base_url, item) for item in edit_candidates if _join_url(base_url, item)), None)
    return download_url, edit_url


def _is_same_origin(url: str, expected_base_url: str) -> bool:
    target = urlparse(url)
    expected = urlparse(expected_base_url)
    return (
        target.scheme.lower() == expected.scheme.lower()
        and target.hostname == expected.hostname
        and (target.port or (443 if target.scheme == "https" else 80))
        == (expected.port or (443 if expected.scheme == "https" else 80))
    )


def _build_download_proxy_url(download_url: Optional[str]) -> Optional[str]:
    if not download_url:
        return None
    return f"/api/presentation/presenton/download?target={quote(download_url, safe='')}"


def _build_presenton_proxy_url(target_url: Optional[str], base_url: str) -> Optional[str]:
    normalized = _join_url(base_url, target_url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{PRESENTON_PROXY_PREFIX}{path}{query}"


def _build_presenton_embed_url(target_url: Optional[str], base_url: str) -> Optional[str]:
    proxied_target = _build_presenton_proxy_url(target_url, base_url)
    if not proxied_target:
        return None
    return f"/api/presentation/presenton/embed?target={quote(proxied_target, safe='')}"


def _decorate_result_urls(result: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    raw_download = result.get("download_url")
    raw_edit = result.get("edit_url")
    proxied_download = _build_download_proxy_url(raw_download)
    proxied_edit = _build_presenton_embed_url(raw_edit, base_url)
    decorated = dict(result)
    if raw_download:
        decorated["download_url_raw"] = raw_download
    if raw_edit:
        decorated["edit_url_raw"] = raw_edit
    if proxied_download:
        decorated["download_url"] = proxied_download
    if proxied_edit:
        decorated["edit_url"] = proxied_edit
    return decorated


def _estimate_progress(status: str, message: str) -> int:
    status_l = str(status or "").lower()
    message_l = str(message or "").lower()
    if status_l in {"completed", "done", "success", "succeeded"}:
        return 100
    if "outline" in message_l or "大纲" in message_l:
        return 20
    if "layout" in message_l or "版式" in message_l:
        return 40
    if "generating slide" in message_l or "generating slides" in message_l or "正在生成页面" in message_l or "整理最终页面" in message_l:
        return 68
    if "fetching asset" in message_l or "素材" in message_l:
        return 88
    if "saving" in message_l or "export" in message_l or "导出" in message_l or "保存" in message_l:
        return 95
    return 10 if status_l == "pending" else 0


def _translate_progress_message(message: str) -> str:
    raw = str(message or "").strip()
    if not raw:
        return ""

    direct_map = {
        "Creating presentation task": "正在创建演示任务",
        "Loading template layout": "正在加载模板版式",
        "Preparing ordered slide layout": "正在整理页级版式结构",
        "Selecting layout for each slide": "正在为每一页选择版式",
        "Selecting layout for slide": "正在为当前页面选择版式",
        "Generating slides": "正在生成页面",
        "Finalizing slides": "正在整理最终页面",
        "Exporting PPT": "正在导出 PPT",
        "Fetching assets": "正在加载页面素材",
        "Fetching asset": "正在加载页面素材",
        "Saving presentation": "正在保存演示文稿",
        "Task submitted": "任务已提交",
        "Presentation generation completed": "PPT 生成完成",
    }
    if raw in direct_map:
        return direct_map[raw]

    translated = raw
    regex_rules: List[Tuple[re.Pattern[str], str]] = [
        (re.compile(r"^Generating slides\s+(\d+)\s*/\s*(\d+)$", re.IGNORECASE), r"正在生成页面 \1/\2"),
        (re.compile(r"^Finalizing slides\s+(\d+)\s*/\s*(\d+)$", re.IGNORECASE), r"正在整理最终页面 \1/\2"),
        (re.compile(r"^Selecting layout for each slide(?:\s*\((\d+)\s*/\s*(\d+)\))?$", re.IGNORECASE), r"正在为每一页选择版式"),
        (re.compile(r"^Selecting layout for slide\s+(\d+)\s*/\s*(\d+)$", re.IGNORECASE), r"正在为页面 \1/\2 选择版式"),
        (re.compile(r"^Fetching assets?\s+(\d+)\s*/\s*(\d+)$", re.IGNORECASE), r"正在加载页面素材 \1/\2"),
        (re.compile(r"^Saving(?:\s+presentation)?$", re.IGNORECASE), r"正在保存演示文稿"),
        (re.compile(r"^Exporting(?:\s+to)?\s+pptx?$", re.IGNORECASE), r"正在导出 PPT"),
    ]
    for pattern, replacement in regex_rules:
        if pattern.search(translated):
            translated = pattern.sub(replacement, translated)
            break

    return translated


def _coerce_progress_value(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 1:
        numeric *= 100
    return int(max(0, min(100, round(numeric))))


def _extract_progress_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    direct_keys = ("progress", "percentage", "percent", "completion")
    for key in direct_keys:
        if key in payload:
            coerced = _coerce_progress_value(payload.get(key))
            if coerced is not None:
                return coerced

    data = payload.get("data")
    if isinstance(data, dict):
        for key in direct_keys:
            if key in data:
                coerced = _coerce_progress_value(data.get(key))
                if coerced is not None:
                    return coerced

    message = str(payload.get("message") or "")
    ratio_match = None
    if message:
        import re

        percent_match = re.search(r"(\d{1,3})\s*%", message)
        if percent_match:
            coerced = _coerce_progress_value(percent_match.group(1))
            if coerced is not None:
                return coerced
        ratio_match = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", message)
    if ratio_match:
        done = float(ratio_match.group(1))
        total = float(ratio_match.group(2))
        if total > 0:
            return _coerce_progress_value(done / total)
    return None


def _extract_status_value(payload: Dict[str, Any]) -> str:
    direct = str(payload.get("status") or payload.get("state") or "").strip().lower()
    if direct:
        return direct
    data = payload.get("data")
    if isinstance(data, dict):
        nested = str(data.get("status") or data.get("state") or data.get("task_status") or "").strip().lower()
        if nested:
            return nested
    return "pending"


def _extract_status_message(payload: Dict[str, Any]) -> str:
    message = str(payload.get("message") or payload.get("detail") or payload.get("error_message") or "").strip()
    if message:
        return _translate_progress_message(message)
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        nested_error = str(
            error_payload.get("detail")
            or error_payload.get("message")
            or error_payload.get("error")
            or ""
        ).strip()
        if nested_error:
            return _translate_progress_message(nested_error)
    data = payload.get("data")
    if isinstance(data, dict):
        nested_message = str(data.get("message") or data.get("detail") or "").strip()
        if nested_message:
            return _translate_progress_message(nested_message)
    return ""


def _rewrite_presenton_text_payload(content: str, base_url: str, content_type: str = "") -> str:
    # Rewrite HTML/CSS asset references so all resources stay in backend proxy.
    lowered_content_type = str(content_type or "").lower()
    parsed_base = urlparse(base_url)
    host_candidates = set(LOCAL_HOST_CANDIDATES)
    if parsed_base.hostname:
        host_candidates.add(parsed_base.hostname.lower())
    host_pattern = "|".join(sorted((re.escape(host) for host in host_candidates), key=len, reverse=True))
    absolute_local_ref_re = re.compile(
        rf"https?://(?:{host_pattern})(?::\d+)?(?P<path>/[^\s\"'<>]*)?"
    )

    rewritten = absolute_local_ref_re.sub(
        lambda match: f"{PRESENTON_PROXY_PREFIX}{match.group('path') or '/'}",
        content,
    )
    if "text/html" in lowered_content_type:
        rewritten = ROOT_RELATIVE_REF_RE.sub(
            lambda match: f"{match.group(1)}{PRESENTON_PROXY_PREFIX}/{match.group(2)}",
            rewritten,
        )
        # Next.js App Router uses assetPrefix to resolve deferred chunk URLs. Keep it on the
        # proxy prefix so runtime-loaded scripts do not escape to frontend `/_next/*`.
        rewritten = rewritten.replace(
            '\\"assetPrefix\\":\\"\\"',
            f'\\"assetPrefix\\":\\"{PRESENTON_PROXY_PREFIX}\\"',
        )
        rewritten = rewritten.replace(
            '"assetPrefix":""',
            f'"assetPrefix":"{PRESENTON_PROXY_PREFIX}"',
        )
        for source_text, target_text in PRESENTON_UI_TRANSLATIONS:
            if source_text in rewritten:
                rewritten = rewritten.replace(source_text, target_text)
    elif "javascript" in lowered_content_type:
        rewritten = rewritten.replace(
            'd.p="/_next/"',
            f'd.p="{PRESENTON_PROXY_PREFIX}/_next/"',
        )
        rewritten = rewritten.replace(
            '__webpack_require__.p="/_next/"',
            f'__webpack_require__.p="{PRESENTON_PROXY_PREFIX}/_next/"',
        )
    elif "text/css" in lowered_content_type:
        rewritten = ROOT_RELATIVE_REF_RE.sub(
            lambda match: f"{match.group(1)}{PRESENTON_PROXY_PREFIX}/{match.group(2)}",
            rewritten,
        )
        rewritten = CSS_ROOT_RELATIVE_URL_RE.sub(
            lambda match: f"url({match.group('quote')}{PRESENTON_PROXY_PREFIX}/{match.group('path')}{match.group('quote')})",
            rewritten,
        )
    return rewritten


def _inject_presenton_proxy_bootstrap_script(html: str) -> str:
    if not html or "__presentonProxyBootstrap" in html:
        return html

    proxy_local_hosts = json.dumps(sorted(LOCAL_HOST_CANDIDATES), ensure_ascii=False)
    script = f"""
<script>
(function() {{
  if (window.__presentonProxyBootstrap) return;
  window.__presentonProxyBootstrap = true;
  const proxyPrefix = {json.dumps(PRESENTON_PROXY_PREFIX)};
  const proxyLocalHosts = new Set({proxy_local_hosts});
  const passthroughSchemes = /^(data:|blob:|javascript:|mailto:|tel:)/i;

  function rewriteUrl(rawValue) {{
    if (rawValue === null || rawValue === undefined || rawValue === '') return rawValue;
    const original = String(rawValue);
    if (passthroughSchemes.test(original)) return original;

    try {{
      const absolute = new URL(original, window.location.origin);
      const host = String(absolute.hostname || '').toLowerCase();
      const isSameOrigin = absolute.origin === window.location.origin;
      const isProxyLocalHost = proxyLocalHosts.has(host);
      if (!isSameOrigin && !isProxyLocalHost) return original;
      if (absolute.pathname.startsWith(proxyPrefix)) {{
        return original.startsWith('http://') || original.startsWith('https://')
          ? absolute.toString()
          : `${{absolute.pathname}}${{absolute.search}}${{absolute.hash}}`;
      }}
      if (!absolute.pathname.startsWith('/')) return original;
      absolute.pathname = absolute.pathname === '/' ? proxyPrefix : `${{proxyPrefix}}${{absolute.pathname}}`;
      return original.startsWith('http://') || original.startsWith('https://')
        ? absolute.toString()
        : `${{absolute.pathname}}${{absolute.search}}${{absolute.hash}}`;
    }} catch (_error) {{
      return original;
    }}
  }}

  function rewriteSrcset(rawValue) {{
    if (!rawValue || typeof rawValue !== 'string') return rawValue;
    return rawValue
      .split(',')
      .map((entry) => {{
        const trimmed = entry.trim();
        if (!trimmed) return trimmed;
        const match = trimmed.match(/^(\\S+)(\\s+.+)?$/);
        if (!match) return trimmed;
        const rewrittenUrl = rewriteUrl(match[1]);
        return `${{rewrittenUrl}}${{match[2] || ''}}`;
      }})
      .join(', ');
  }}

  function rewriteStyleValue(rawValue) {{
    if (!rawValue || typeof rawValue !== 'string') return rawValue;
    return rawValue.replace(/url\\((['"]?)(.*?)\\1\\)/gi, function(_full, quote, assetUrl) {{
      const rewrittenUrl = rewriteUrl(assetUrl);
      const nextQuote = quote || '';
      return `url(${{nextQuote}}${{rewrittenUrl}}${{nextQuote}})`;
    }});
  }}

  function rewriteElementUrls(root) {{
    const elements = [];
    if (root && root.nodeType === Node.ELEMENT_NODE) {{
      elements.push(root);
    }}
    if (root && root.querySelectorAll) {{
      root.querySelectorAll('[src], [srcset], [href], [poster], [action], [formaction], [style]').forEach((node) => {{
        elements.push(node);
      }});
    }}
    elements.forEach((element) => {{
      if (!element || !element.getAttribute || !element.setAttribute) return;
      ['src', 'href', 'poster', 'action', 'formaction'].forEach((attrName) => {{
        const rawValue = element.getAttribute(attrName);
        if (!rawValue) return;
        const rewrittenValue = rewriteUrl(rawValue);
        if (rewrittenValue && rewrittenValue !== rawValue) {{
          element.setAttribute(attrName, rewrittenValue);
        }}
      }});
      const rawSrcset = element.getAttribute('srcset');
      if (rawSrcset) {{
        const rewrittenSrcset = rewriteSrcset(rawSrcset);
        if (rewrittenSrcset && rewrittenSrcset !== rawSrcset) {{
          element.setAttribute('srcset', rewrittenSrcset);
        }}
      }}
      const rawStyle = element.getAttribute('style');
      if (rawStyle) {{
        const rewrittenStyle = rewriteStyleValue(rawStyle);
        if (rewrittenStyle && rewrittenStyle !== rawStyle) {{
          element.setAttribute('style', rewrittenStyle);
        }}
      }}
    }});
  }}

  const originalFetch = window.fetch ? window.fetch.bind(window) : null;
  if (originalFetch) {{
    window.fetch = function(input, init) {{
      if (typeof input === 'string' || input instanceof URL) {{
        return originalFetch(rewriteUrl(input), init);
      }}
      if (window.Request && input instanceof Request) {{
        const rewritten = rewriteUrl(input.url);
        if (rewritten !== input.url) {{
          return originalFetch(new Request(rewritten, input), init);
        }}
      }}
      return originalFetch(input, init);
    }};
  }}

  if (window.XMLHttpRequest && window.XMLHttpRequest.prototype) {{
    const originalOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
      return originalOpen.call(this, method, rewriteUrl(url), ...rest);
    }};
  }}

  if (window.EventSource) {{
    const OriginalEventSource = window.EventSource;
    const ProxyEventSource = function(url, config) {{
      return new OriginalEventSource(rewriteUrl(url), config);
    }};
    try {{
      ProxyEventSource.prototype = OriginalEventSource.prototype;
      Object.setPrototypeOf(ProxyEventSource, OriginalEventSource);
      ProxyEventSource.CONNECTING = OriginalEventSource.CONNECTING;
      ProxyEventSource.OPEN = OriginalEventSource.OPEN;
      ProxyEventSource.CLOSED = OriginalEventSource.CLOSED;
    }} catch (_error) {{
      // Some browsers limit constructor mutation; the wrapper still works without these assignments.
    }}
    window.EventSource = ProxyEventSource;
  }}

  if (window.history && window.history.pushState) {{
    const originalPushState = window.history.pushState.bind(window.history);
    window.history.pushState = function(state, title, url) {{
      return originalPushState(state, title, url == null ? url : rewriteUrl(url));
    }};
  }}

  if (window.history && window.history.replaceState) {{
    const originalReplaceState = window.history.replaceState.bind(window.history);
    window.history.replaceState = function(state, title, url) {{
      return originalReplaceState(state, title, url == null ? url : rewriteUrl(url));
    }};
  }}

  try {{
    const locationProto = Object.getPrototypeOf(window.location);
    if (locationProto && typeof locationProto.assign === 'function') {{
      const originalAssign = locationProto.assign.bind(window.location);
      locationProto.assign = function(url) {{
        return originalAssign(rewriteUrl(url));
      }};
    }}
    if (locationProto && typeof locationProto.replace === 'function') {{
      const originalReplace = locationProto.replace.bind(window.location);
      locationProto.replace = function(url) {{
        return originalReplace(rewriteUrl(url));
      }};
    }}
  }} catch (_error) {{
    // Some browsers lock Location.prototype; history/fetch interception is still enough.
  }}

  if (window.open) {{
    const originalOpenWindow = window.open.bind(window);
    window.open = function(url, ...rest) {{
      return originalOpenWindow(url == null ? url : rewriteUrl(url), ...rest);
    }};
  }}

  function isEditBannerText(text) {{
    if (!text || typeof text !== 'string') return false;
    const normalized = text.replace(/\\s+/g, ' ').trim().toLowerCase();
    return (
      normalized.includes('want to edit? use your computer to edit.') ||
      normalized.includes('use your computer to edit.') ||
      (normalized.includes('want to edit') && normalized.includes('computer to edit'))
    );
  }}

  function getOwnText(node) {{
    if (!node || !node.childNodes) return '';
    return Array.from(node.childNodes)
      .filter((child) => child && child.nodeType === Node.TEXT_NODE)
      .map((child) => child.nodeValue || '')
      .join(' ')
      .replace(/\\s+/g, ' ')
      .trim();
  }}

  function findBannerContainer(node) {{
    let current = node;
    for (let depth = 0; depth < 4 && current && current !== document.body && current !== document.documentElement; depth += 1) {{
      const rect = typeof current.getBoundingClientRect === 'function'
        ? current.getBoundingClientRect()
        : {{ top: 9999, height: 0 }};
      const style = window.getComputedStyle(current);
      const topRegion = rect.top <= 180;
      const smallEnough = rect.height > 0 && rect.height <= 120;
      const ownText = getOwnText(current);
      if ((isEditBannerText(ownText) || isEditBannerText(current.textContent || '')) && topRegion && smallEnough) {{
        return current;
      }}
      if ((style.position === 'sticky' || style.position === 'fixed') && topRegion && rect.height <= 140) {{
        return current;
      }}
      current = current.parentElement;
    }}
    return null;
  }}

  function hideEditBanner(root) {{
    const scope = root && root.querySelectorAll ? root : document;
    const candidates = scope.querySelectorAll
      ? scope.querySelectorAll('div, section, aside, header, p, span')
      : [];
    candidates.forEach((node) => {{
      const ownText = getOwnText(node);
      if (!ownText || ownText.length > 120 || !isEditBannerText(ownText)) return;
      const banner = findBannerContainer(node) || node;
      const rect = typeof banner.getBoundingClientRect === 'function'
        ? banner.getBoundingClientRect()
        : {{ top: 9999, height: 0 }};
      if (
        banner === document.body ||
        banner === document.documentElement ||
        rect.height <= 0 ||
        rect.height > 140 ||
        rect.top > 220
      ) {{
        return;
      }}
      banner.style.setProperty('display', 'none', 'important');
      banner.style.setProperty('height', '0', 'important');
      banner.style.setProperty('min-height', '0', 'important');
      banner.style.setProperty('overflow', 'hidden', 'important');
      banner.setAttribute('data-presenton-hidden-banner', 'true');
    }});
  }}

  function startEditBannerObserver() {{
    if (!window.MutationObserver || window.__presentonEditBannerObserverStarted) return;
    window.__presentonEditBannerObserverStarted = true;
    const observer = new MutationObserver((mutations) => {{
      mutations.forEach((mutation) => {{
        mutation.addedNodes.forEach((node) => {{
          if (!node || node.nodeType !== Node.ELEMENT_NODE) return;
          rewriteElementUrls(node);
          hideEditBanner(node);
        }});
        if (mutation.type === 'attributes' && mutation.target && mutation.target.nodeType === Node.ELEMENT_NODE) {{
          rewriteElementUrls(mutation.target);
        }}
        if (mutation.type === 'characterData' && mutation.target && mutation.target.parentElement) {{
          hideEditBanner(mutation.target.parentElement);
        }}
      }});
    }});
    observer.observe(document.documentElement, {{
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['src', 'srcset', 'href', 'poster', 'action', 'formaction', 'style']
    }});
  }}

  function runEditBannerCleanup() {{
    rewriteElementUrls(document);
    hideEditBanner(document);
    startEditBannerObserver();
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', runEditBannerCleanup, {{ once: true }});
  }} else {{
    runEditBannerCleanup();
  }}

  let cleanupAttempts = 0;
  const cleanupTimer = window.setInterval(() => {{
    runEditBannerCleanup();
    cleanupAttempts += 1;
    if (cleanupAttempts >= 40) {{
      window.clearInterval(cleanupTimer);
    }}
  }}, 400);
}})();
</script>
""".strip()

    lower_html = html.lower()
    first_script_index = lower_html.find("<script")
    if first_script_index >= 0:
        return f"{html[:first_script_index]}{script}{html[first_script_index:]}"
    head_index = lower_html.rfind("</head>")
    if head_index >= 0:
        return f"{html[:head_index]}{script}{html[head_index:]}"
    return f"{script}{html}"


def _inject_template_preview_i18n_script(html: str) -> str:
    if not html or "__presentonTemplatePreviewI18n" in html:
        return html

    direct_map = json.dumps(PRESENTON_TEMPLATE_PREVIEW_TEXT_MAP, ensure_ascii=False)
    regex_rules = json.dumps(PRESENTON_TEMPLATE_PREVIEW_REGEX_RULES, ensure_ascii=False)
    script = f"""
<script>
(function() {{
  if (window.__presentonTemplatePreviewI18n) return;
  window.__presentonTemplatePreviewI18n = true;
  const directMap = {direct_map};
  const regexRules = {regex_rules}.map(([pattern, replacement]) => [new RegExp(pattern, 'g'), replacement]);
  const excludedTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT']);
  let running = false;

  function translateText(value) {{
    if (!value || typeof value !== 'string') return value;
    let next = value;
    for (const [sourceText, targetText] of Object.entries(directMap)) {{
      if (next.includes(sourceText)) {{
        next = next.split(sourceText).join(targetText);
      }}
    }}
    for (const [pattern, replacement] of regexRules) {{
      next = next.replace(pattern, replacement);
    }}
    return next;
  }}

  function translateAttribute(element, attrName) {{
    if (!element || !element.getAttribute) return;
    const rawValue = element.getAttribute(attrName);
    if (!rawValue) return;
    const translated = translateText(rawValue);
    if (translated !== rawValue) {{
      element.setAttribute(attrName, translated);
    }}
  }}

  function translateNodeTree(root) {{
    if (!root || running) return;
    running = true;
    try {{
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let current;
      while ((current = walker.nextNode())) {{
        const parent = current.parentElement;
        if (!parent || excludedTags.has(parent.tagName)) continue;
        const rawValue = current.nodeValue;
        const translated = translateText(rawValue);
        if (translated !== rawValue) {{
          current.nodeValue = translated;
        }}
      }}

      const elements = root.querySelectorAll
        ? root.querySelectorAll('[title], [aria-label], input[placeholder], textarea[placeholder], img[alt], iframe[title]')
        : [];
      elements.forEach((element) => {{
        translateAttribute(element, 'title');
        translateAttribute(element, 'aria-label');
        translateAttribute(element, 'placeholder');
        translateAttribute(element, 'alt');
      }});

      if (document.title) {{
        document.title = translateText(document.title);
      }}
    }} finally {{
      running = false;
    }}
  }}

  function runTranslate(target) {{
    translateNodeTree(target || document.body || document.documentElement);
  }}

  const startObserver = () => {{
    const observer = new MutationObserver((mutations) => {{
      if (running) return;
      for (const mutation of mutations) {{
        if (mutation.type === 'characterData') {{
          translateNodeTree(mutation.target.parentElement || document.body || document.documentElement);
          continue;
        }}
        mutation.addedNodes.forEach((node) => {{
          if (node && node.nodeType === Node.TEXT_NODE) {{
            translateNodeTree(node.parentElement || document.body || document.documentElement);
          }} else if (node && node.nodeType === Node.ELEMENT_NODE) {{
            translateNodeTree(node);
          }}
        }});
      }}
    }});
    observer.observe(document.documentElement, {{
      subtree: true,
      childList: true,
      characterData: true
    }});
  }};

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', () => {{
      runTranslate();
      startObserver();
    }}, {{ once: true }});
  }} else {{
    runTranslate();
    startObserver();
  }}

  let attempts = 0;
  const timer = setInterval(() => {{
    runTranslate();
    attempts += 1;
    if (attempts >= 30) {{
      clearInterval(timer);
    }}
  }}, 400);
}})();
</script>
""".strip()

    lower_html = html.lower()
    body_index = lower_html.rfind("</body>")
    if body_index >= 0:
        return f"{html[:body_index]}{script}{html[body_index:]}"
    return f"{html}{script}"


def _build_proxy_upstream_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in PROXY_CACHE_REQUEST_HEADERS or lowered in {"host", "content-length"}:
            continue
        headers[key] = value
    if DEFAULT_PRESENTON_API_KEY and "authorization" not in {k.lower() for k in headers}:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"
    return headers


def _filter_proxy_response_headers(headers: Dict[str, str], base_url: str) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS:
            continue
        if lowered in PROXY_CACHE_RESPONSE_HEADERS or lowered in {"content-security-policy", "content-length", "content-encoding"}:
            continue
        if lowered == "location":
            proxied_location = _build_presenton_proxy_url(value, base_url)
            filtered[key] = proxied_location or value
            continue
        filtered[key] = value
    return filtered


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = REQUEST_TIMEOUT_SEC,
) -> Dict[str, Any]:
    try:
        response = _PRESENTON_SESSION.request(method=method, url=url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Presenton request failed: {exc}") from exc

    raw_text = response.text or ""
    try:
        data = response.json() if raw_text else {}
    except Exception:
        data = {"raw_text": raw_text[:2000]}

    if response.status_code >= 400:
        detail = (
            data.get("message")
            or data.get("error")
            or data.get("detail")
            or data.get("raw_text")
            or f"Presenton API error ({response.status_code})"
        )
        raise HTTPException(status_code=502, detail=str(detail))
    return data


def _request_stream(
    method: str,
    url: str,
    headers: Dict[str, str],
    timeout: float = REQUEST_TIMEOUT_SEC,
):
    try:
        response = _PRESENTON_SESSION.request(
            method=method,
            url=url,
            headers=headers,
            stream=True,
            timeout=(10, timeout),
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Presenton stream request failed: {exc}") from exc

    if response.status_code >= 400:
        raw_text = ""
        try:
            raw_text = response.text or ""
        except Exception:
            raw_text = ""
        try:
            data = response.json() if raw_text else {}
        except Exception:
            data = {"raw_text": raw_text[:2000]}
        detail = (
            data.get("message")
            or data.get("error")
            or data.get("detail")
            or data.get("raw_text")
            or f"Presenton API error ({response.status_code})"
        )
        response.close()
        raise HTTPException(status_code=502, detail=str(detail))
    return response


def _extract_slide_title_from_markdown(slide_markdown: str) -> str:
    lines = [str(line or "").strip() for line in str(slide_markdown or "").splitlines()]
    for raw_line in lines:
        line = raw_line.lstrip("#").strip()
        if not line:
            continue
        if line.startswith(("-", "*", ">")):
            continue
        if re.match(r"^\d+[\.\) 、]", line):
            continue
        return line[:120]
    for raw_line in lines:
        line = raw_line.strip()
        if line:
            return line[:120]
    return "演示文稿"


def _derive_presentation_title(req: PresentonGenerateRequest) -> str:
    if isinstance(req.slides_markdown, list) and req.slides_markdown:
        title = _extract_slide_title_from_markdown(req.slides_markdown[0])
        if title:
            return title
    prompt = str(req.prompt or "").strip()
    if not prompt:
        return "演示文稿"
    first_line = prompt.splitlines()[0].strip()
    return first_line[:120] if first_line else "演示文稿"


def _extract_slide_titles(req: PresentonGenerateRequest) -> List[str]:
    if not isinstance(req.slides_markdown, list):
        return []
    titles: List[str] = []
    for slide in req.slides_markdown:
        title = _extract_slide_title_from_markdown(str(slide or ""))
        if title:
            titles.append(title[:120])
    return titles[:40]


def _build_ordered_runtime_prompt(req: PresentonGenerateRequest) -> str:
    slide_titles = _extract_slide_titles(req)
    deck_title = _derive_presentation_title(req)
    slide_count = len(slide_titles) or int(req.n_slides or 8)
    lines = [
        f"请根据已确认的页级大纲生成一份 {slide_count} 页中文 PPT。",
        f"演示主题：{deck_title}",
        "标题要求：封面页可使用演示主题；从第 2 页开始，必须使用对应页级大纲中的标题作为页面主标题，不得把演示主题重复写成每一页的大标题。",
        "内容要求：每一页只展开当前页级大纲，不要把 language、内容导向、页面角色、展开要求、讲解备注、参考素材等控制文字直接显示到页面中。",
        "表达要求：如果页级大纲已经提供了明确页标题，必须保留该标题的核心含义，不要统一改写成“XX汇报”“XX报告”“背景分析”“工作总结”这类泛化标题。",
    ]
    if slide_titles:
        lines.append("页标题清单：")
        lines.extend([f"{idx + 1}. {title}" for idx, title in enumerate(slide_titles)])
    return "\n".join(lines)


def _copy_presenton_request(req: PresentonGenerateRequest, **updates: Any) -> PresentonGenerateRequest:
    if hasattr(req, "model_copy"):
        return req.model_copy(update=updates)  # type: ignore[attr-defined]
    return req.copy(update=updates)  # type: ignore[attr-defined]


def _extract_layout_schema_properties(layout: Dict[str, Any]) -> Dict[str, Any]:
    schema = layout.get("json_schema")
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _schema_contains_image_slot(fragment: Any) -> bool:
    if isinstance(fragment, dict):
        fragment_type = str(fragment.get("type") or "").strip().lower()
        properties = fragment.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                lowered_key = str(key or "").strip().lower()
                if any(token in lowered_key for token in ("image", "photo", "picture", "illustration", "backgroundimage", "mapimage", "__image_url__", "__image_prompt__")):
                    return True
                if _schema_contains_image_slot(value):
                    return True

        required = fragment.get("required")
        if isinstance(required, list):
            for item in required:
                lowered_required = str(item or "").strip().lower()
                if any(token in lowered_required for token in ("image", "photo", "picture", "illustration", "backgroundimage", "mapimage", "__image_url__", "__image_prompt__")):
                    return True

        for key in ("items", "additionalProperties"):
            if _schema_contains_image_slot(fragment.get(key)):
                return True

        for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
            value = fragment.get(key)
            if isinstance(value, list) and any(_schema_contains_image_slot(item) for item in value):
                return True

        if fragment_type == "object" and isinstance(properties, dict) and "__image_url__" in properties:
            return True

    elif isinstance(fragment, list):
        return any(_schema_contains_image_slot(item) for item in fragment)

    return False


def _layout_requires_image(layout: Dict[str, Any]) -> bool:
    id_text = " ".join(
        [
            str(layout.get("id") or ""),
            str(layout.get("name") or ""),
            str(layout.get("description") or ""),
        ]
    ).lower()
    if any(token in id_text for token in ("image", "photo", "picture", "illustration", "backgroundimage", "mapimage")):
        return True
    for key in _extract_layout_schema_properties(layout).keys():
        lowered = str(key or "").strip().lower()
        if any(token in lowered for token in ("image", "photo", "picture", "backgroundimage", "mapimage")):
            return True
    if _schema_contains_image_slot(layout.get("json_schema")):
        return True
    return False


def _score_layout_candidate(
    layout: Dict[str, Any],
    slide_markdown: str,
    slide_index: int,
    total_slides: int,
    used_counts: Dict[str, int],
    previous_layout_id: Optional[str],
    prefer_no_image: bool,
) -> int:
    layout_id = str(layout.get("id") or "").strip()
    meta_text = " ".join(
        [
            layout_id,
            str(layout.get("name") or ""),
            str(layout.get("description") or ""),
            " ".join(_extract_layout_schema_properties(layout).keys()),
        ]
    ).lower()
    slide_text = str(slide_markdown or "").lower()
    title_text = _extract_slide_title_from_markdown(slide_markdown).lower()
    bullet_lines = [
        line for line in str(slide_markdown or "").splitlines()
        if str(line or "").strip().startswith(("-", "*")) or re.match(r"^\s*\d+[\.\) 、]", str(line or ""))
    ]
    bullet_count = len(bullet_lines)
    wants_cover = slide_index == 0 or any(token in title_text for token in ("封面", "标题", "开场", "cover", "title"))
    wants_toc = any(token in slide_text for token in ("目录", "议程", "大纲", "agenda", "contents", "toc"))
    wants_metrics = any(
        token in slide_text
        for token in ("数据", "指标", "趋势", "统计", "对比", "增长", "营收", "预算", "图表", "chart", "metric", "table", "kpi")
    )
    wants_process = any(
        token in slide_text
        for token in ("流程", "步骤", "路径", "计划", "阶段", "里程碑", "执行", "推进", "roadmap", "process", "timeline")
    )
    wants_summary = slide_index == (total_slides - 1) or any(
        token in slide_text for token in ("总结", "结论", "建议", "下一步", "summary", "conclusion", "takeaway")
    )
    wants_quote = any(token in slide_text for token in ("洞察", "观点", "金句", "引用", "quote", "insight"))

    score = 0
    if prefer_no_image and not _layout_requires_image(layout):
        score += 6
    if prefer_no_image and _layout_requires_image(layout):
        score -= 10
    if wants_cover and any(token in meta_text for token in ("intro", "title", "cover", "pitchdeck")):
        score += 24
    if wants_cover and any(token in meta_text for token in ("chart", "metric", "table", "bullet", "grid")):
        score -= 18
    if wants_toc and any(token in meta_text for token in ("table-of-contents", "contents")):
        score -= 16
    if wants_toc and any(token in meta_text for token in ("agenda", "sections", "list")):
        score += 18
    if wants_metrics and any(token in meta_text for token in ("chart", "metric", "table", "stats", "data")):
        score += 12
    if wants_process and any(token in meta_text for token in ("process", "timeline", "roadmap", "stage", "path", "steps")):
        score += 10
    if wants_summary and any(token in meta_text for token in ("summary", "quote", "takeaway", "metric", "insight")):
        score += 10
    if wants_quote and any(token in meta_text for token in ("quote", "insight", "highlight")):
        score += 9
    if bullet_count >= 4 and any(token in meta_text for token in ("bullet", "grid", "card", "list")):
        score += 7
    if bullet_count >= 2 and any(token in meta_text for token in ("bullet", "list", "description")):
        score += 4
    if any(token in meta_text for token in ("description", "grid", "bullet", "metric", "chart")):
        score += 1

    used = int(used_counts.get(layout_id, 0) or 0)
    score -= used * 4
    if previous_layout_id and previous_layout_id == layout_id:
        score -= 8
    return score


def _build_ordered_layout_payload(req: PresentonGenerateRequest, layout_payload: Dict[str, Any]) -> Dict[str, Any]:
    slides_markdown = req.slides_markdown if isinstance(req.slides_markdown, list) else []
    if not slides_markdown:
        raise HTTPException(status_code=400, detail="slides_markdown is required for ordered layout generation")

    source_layouts = layout_payload.get("slides")
    if not isinstance(source_layouts, list) or not source_layouts:
        raise HTTPException(status_code=502, detail="Presenton template layout is empty")

    prefer_no_image = _prefer_no_image(req)
    image_safe_layouts = [item for item in source_layouts if isinstance(item, dict) and not _layout_requires_image(item)]
    all_layouts = [item for item in source_layouts if isinstance(item, dict)]
    used_counts: Dict[str, int] = {}
    selected_layouts: List[Dict[str, Any]] = []
    previous_layout_id: Optional[str] = None

    for index, slide_markdown in enumerate(slides_markdown):
        pool = (image_safe_layouts or all_layouts) if prefer_no_image else all_layouts
        chosen = max(
            pool,
            key=lambda item: _score_layout_candidate(
                item, slide_markdown, index, len(slides_markdown), used_counts, previous_layout_id, prefer_no_image
            ),
        )

        layout_id = str(chosen.get("id") or "").strip()
        if not layout_id:
            continue
        selected_layouts.append(
            {
                "id": layout_id,
                "name": chosen.get("name"),
                "description": chosen.get("description"),
                "json_schema": chosen.get("json_schema") or {},
            }
        )
        used_counts[layout_id] = used_counts.get(layout_id, 0) + 1
        previous_layout_id = layout_id

    if len(selected_layouts) != len(slides_markdown):
        raise HTTPException(status_code=502, detail="Failed to resolve ordered slide layouts from selected template")

    return {
        "name": str(layout_payload.get("name") or req.template or "general"),
        "ordered": True,
        "slides": selected_layouts,
    }


def _fetch_presenton_template_group(base_url: str, headers: Dict[str, str], template_id: str) -> Dict[str, Any]:
    errors: List[str] = []
    for candidate in _template_retry_candidates(template_id):
        cache_key = f"{base_url}::{candidate}"
        with _TEMPLATE_GROUP_CACHE_LOCK:
            cached = _TEMPLATE_GROUP_CACHE.get(cache_key)
            if cached:
                return dict(cached)
        resolved = TEMPLATE_GROUP_PATH.replace("{template_id}", requests.utils.quote(candidate, safe=""))
        url = f"{base_url}{resolved}"
        try:
            data = _request_json("GET", url, headers, payload=None, timeout=max(REQUEST_TIMEOUT_SEC, 20))
            if isinstance(data, dict) and isinstance(data.get("slides"), list):
                with _TEMPLATE_GROUP_CACHE_LOCK:
                    _TEMPLATE_GROUP_CACHE[cache_key] = dict(data)
                return data
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue
    detail = errors[-1] if errors else "Template group layout not found"
    raise HTTPException(status_code=404, detail=detail)


def _parse_stream_event_payload(payload_text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(payload_text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stream_prepared_presentation(
    task_id: str,
    base_url: str,
    headers: Dict[str, str],
    presentation_id: str,
    total_slides: int,
) -> Dict[str, Any]:
    stream_path = STREAM_PRESENTATION_PATH_TEMPLATE.replace("{presentation_id}", presentation_id)
    stream_url = f"{base_url}{stream_path}"
    stream_headers = dict(headers)
    stream_headers.pop("Content-Type", None)
    stream_headers["Accept"] = "text/event-stream"

    response = _request_stream("GET", stream_url, stream_headers, timeout=max(POLL_TIMEOUT_SEC, REQUEST_TIMEOUT_SEC))
    generated_slides = 0
    completed_payload: Dict[str, Any] = {}
    data_lines: List[str] = []

    with response:
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = str(raw_line).rstrip("\r")
            if not line:
                payload_text = "\n".join(data_lines).strip()
                data_lines = []
                if not payload_text:
                    continue
                event_payload = _parse_stream_event_payload(payload_text)
                if not event_payload:
                    continue
                if event_payload.get("detail") or event_payload.get("error"):
                    detail = event_payload.get("detail") or event_payload.get("error")
                    raise HTTPException(status_code=502, detail=str(detail))

                payload_type = str(event_payload.get("type") or "").strip().lower()
                if payload_type == "chunk":
                    chunk = event_payload.get("chunk")
                    if isinstance(chunk, str):
                        chunk_text = chunk.strip()
                        if chunk_text.startswith("{") and '"layout"' in chunk_text:
                            try:
                                slide_payload = json.loads(chunk_text)
                            except Exception:
                                slide_payload = {}
                            try:
                                slide_index = int(slide_payload.get("index"))
                                generated_slides = max(generated_slides, slide_index + 1)
                            except Exception:
                                generated_slides += 1
                            progress = min(90, 45 + int((generated_slides / max(1, total_slides)) * 42))
                            message = f"正在生成页面 {generated_slides}/{total_slides}"
                            if generated_slides >= total_slides:
                                message = f"正在整理最终页面 {generated_slides}/{total_slides}"
                            _upsert_ordered_task(task_id, status="pending", progress=progress, message=message)
                elif payload_type == "complete" and str(event_payload.get("key") or "") == "presentation":
                    value = event_payload.get("value")
                    if isinstance(value, dict):
                        completed_payload = value
                continue

            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())

    return completed_payload


def _extract_markdown_json(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}

    fenced_match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidate = fenced_match.group(1).strip() if fenced_match else text

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    first = candidate.find("{")
    last = candidate.rfind("}")
    if first >= 0 and last > first:
        maybe_json = candidate[first:last + 1]
        try:
            parsed = json.loads(maybe_json)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _invoke_outline_llm(prompt: str, model_backend: str) -> Tuple[str, Optional[str]]:
    timeout_sec = max(0.0, OUTLINE_LLM_TIMEOUT_SEC)
    if timeout_sec <= 0:
        return str(ask_llm(prompt, model_type=model_backend) or ""), None

    future = _OUTLINE_LLM_EXECUTOR.submit(ask_llm, prompt, model_backend)
    try:
        return str(future.result(timeout=timeout_sec) or ""), None
    except FuturesTimeoutError:
        future.cancel()
        logger.warning(
            "PPT outline generation timed out after %.1fs, backend=%s",
            timeout_sec,
            model_backend,
        )
        return "", "timeout"
    except Exception:
        future.cancel()
        logger.exception("PPT outline generation failed unexpectedly, backend=%s", model_backend)
        return "", "error"


def _sanitize_outline_title(title: Optional[str], fallback: str) -> str:
    value = str(title or "").strip()
    return value[:120] if value else fallback


def _build_fallback_slide_points(topic: str, slide_title: str) -> List[str]:
    topic_label = _sanitize_outline_title(topic, "当前主题")
    slide_label = _sanitize_outline_title(slide_title, "本页")
    if "封面" in slide_label:
        return [
            f"明确演示主题“{topic_label}”的核心方向。",
            "交代汇报对象、汇报场景或使用场合。",
            "概括本次汇报希望回答的关键问题。",
            "点出整体价值主张或预期成果。",
        ]
    if "目录" in slide_label or "摘要" in slide_label:
        return [
            "概览全文章节结构与阅读顺序。",
            "突出 3-4 个最重要的分析模块。",
            "说明每个模块将解决什么问题。",
            "帮助听众快速建立整体认知框架。",
        ]
    if "背景" in slide_label or "现状" in slide_label:
        return [
            f"说明“{topic_label}”的背景、现状或发展阶段。",
            "补充关键事实、业务场景或外部环境信息。",
            "指出当前最突出的矛盾、痛点或变化趋势。",
            "说明这些背景为什么值得进一步分析。",
        ]
    if "问题" in slide_label or "挑战" in slide_label:
        return [
            "拆解当前面临的主要问题或瓶颈。",
            "分析问题形成的关键成因与影响范围。",
            "区分短期现象与长期结构性问题。",
            "明确后续方案设计需要优先解决的焦点。",
        ]
    if "方案" in slide_label or "策略" in slide_label:
        return [
            "提出核心方案或策略主张。",
            "拆分关键模块、执行动作或能力建设项。",
            "说明方案如何回应前述问题与目标。",
            "交代预期收益、边界条件与实施重点。",
        ]
    if "实施" in slide_label or "路径" in slide_label or "执行" in slide_label:
        return [
            "给出阶段化推进路径与关键里程碑。",
            "明确责任分工、资源要求或协同机制。",
            "说明每一阶段的交付物和验收口径。",
            "补充时间节奏、依赖条件与推进建议。",
        ]
    if "指标" in slide_label or "预算" in slide_label or "收益" in slide_label:
        return [
            "列出衡量成效的关键指标或预算维度。",
            "说明指标口径、目标值或区间判断。",
            "关联效率、成本、质量、风险等结果项。",
            "补充可持续跟踪和复盘的观察方式。",
        ]
    if "风险" in slide_label or "保障" in slide_label:
        return [
            "识别实施过程中的主要风险点。",
            "分析风险成因、触发条件与影响程度。",
            "提出针对性的预防措施与应急方案。",
            "说明保障机制、监控频率与责任安排。",
        ]
    if "总结" in slide_label or "行动" in slide_label:
        return [
            "回收全文的核心判断与关键结论。",
            "提炼最值得优先落地的行动项。",
            "明确下一步推进顺序与决策建议。",
            "提示需要继续补充的数据、资源或条件。",
        ]
    return [
        f"说明“{slide_label}”与“{topic_label}”的关系和本页核心结论。",
        "补充关键事实、现状、案例或数据依据。",
        "拆解主要影响因素、分析逻辑或结构要点。",
        "给出对应建议、行动方向或预期结果。",
    ]


def _build_fallback_slide_notes(topic: str, slide_title: str) -> str:
    topic_label = _sanitize_outline_title(topic, "当前主题")
    slide_label = _sanitize_outline_title(slide_title, "本页")
    return (
        f"围绕“{topic_label}”展开“{slide_label}”的详细说明，"
        "可补充定义解释、案例、数据指标、图表建议或落地动作，避免空泛表述。"
    )


def _resolve_outline_content_focus(req: PresentonOutlineRequest) -> Dict[str, Any]:
    raw_focus = str(getattr(req, "content_focus", "") or "").strip().lower()
    if raw_focus in OUTLINE_CONTENT_FOCUS_CONFIG:
        return OUTLINE_CONTENT_FOCUS_CONFIG[raw_focus]

    for key, item in OUTLINE_CONTENT_FOCUS_CONFIG.items():
        label = str(item.get("label") or "").strip().lower()
        if raw_focus and raw_focus == label:
            return OUTLINE_CONTENT_FOCUS_CONFIG[key]

    raw_framework = str(getattr(req, "analysis_framework", "") or "").strip().lower()
    legacy_frameworks = {"4p框架", "swot", "pest", "波特五力", "stp"}
    if raw_framework in legacy_frameworks:
        return OUTLINE_CONTENT_FOCUS_CONFIG["analysis"]

    return OUTLINE_CONTENT_FOCUS_CONFIG["work_report"]


def _build_outline_subtitle(req: PresentonOutlineRequest, focus_config: Dict[str, Any]) -> str:
    focus_label = str(focus_config.get("label") or "工作汇报").strip() or "工作汇报"
    language = str(req.language or "").strip().lower()
    if not language or language in {"chinese", "中文", "简体中文", "simplified chinese", "zh-cn", "zh_cn"}:
        return focus_label
    return f"{focus_label} · {str(req.language or '').strip()}"


def _fallback_outline(req: PresentonOutlineRequest, input_text: str) -> Dict[str, Any]:
    topic = _sanitize_outline_title(input_text.splitlines()[0] if input_text else "", "业务汇报")
    slide_count = max(3, min(40, int(req.n_slides or 8)))
    focus_config = _resolve_outline_content_focus(req)
    section_titles = list(focus_config.get("sections") or [])
    slides: List[Dict[str, Any]] = []
    for idx in range(slide_count):
        title = section_titles[idx] if idx < len(section_titles) else f"补充页 {idx + 1}"
        points = _build_fallback_slide_points(topic, title)
        slides.append(
            {
                "index": idx + 1,
                "title": title,
                "points": points,
                "notes": _build_fallback_slide_notes(topic, title),
            }
        )
    return {
        "title": f"{topic}汇报",
        "subtitle": _build_outline_subtitle(req, focus_config),
        "slides": slides,
    }


def _normalize_outline_payload(payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback

    slides_raw = payload.get("slides")
    if not isinstance(slides_raw, list) or not slides_raw:
        return fallback

    fallback_slides = fallback.get("slides") if isinstance(fallback, dict) else []
    if not isinstance(fallback_slides, list):
        fallback_slides = []

    normalized_slides: List[Dict[str, Any]] = []
    for idx, item in enumerate(slides_raw, start=1):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("heading") or f"第 {idx} 页").strip()
            points_raw = item.get("points") or item.get("bullets") or []
            notes = str(item.get("notes") or item.get("speaker_notes") or "").strip()
        else:
            title = f"第 {idx} 页"
            points_raw = []
            notes = ""

        points: List[str] = []
        if isinstance(points_raw, list):
            points = [str(point).strip() for point in points_raw if str(point).strip()]
        elif isinstance(points_raw, str):
            points = [line.strip("- \t") for line in points_raw.splitlines() if line.strip()]

        fallback_slide = fallback_slides[idx - 1] if (idx - 1) < len(fallback_slides) else {}
        fallback_points_raw = fallback_slide.get("points") if isinstance(fallback_slide, dict) else []
        if isinstance(fallback_points_raw, list):
            fallback_points = [str(point).strip() for point in fallback_points_raw if str(point).strip()]
        elif isinstance(fallback_points_raw, str):
            fallback_points = [line.strip("- \t") for line in fallback_points_raw.splitlines() if line.strip()]
        else:
            fallback_points = []

        if not points:
            points = fallback_points or [
                "补充本页核心观点。",
                "补充关键支撑信息。",
                "补充分析逻辑或事实依据。",
                "补充行动建议与结果预期。",
            ]
        elif len(points) < 4:
            for extra in fallback_points:
                if extra not in points:
                    points.append(extra)
                if len(points) >= 4:
                    break

        if not notes and isinstance(fallback_slide, dict):
            notes = str(fallback_slide.get("notes") or "").strip()

        normalized_slides.append(
            {
                "index": idx,
                "title": title[:120],
                "points": points[:10],
                "notes": notes[:1200],
            }
        )

    return {
        "title": _sanitize_outline_title(payload.get("title"), fallback.get("title", "演示文稿")),
        "subtitle": _sanitize_outline_title(payload.get("subtitle"), fallback.get("subtitle", "")),
        "slides": normalized_slides[:40],
    }


def _build_outline_prompt(req: PresentonOutlineRequest, input_text: str) -> str:
    focus_config = _resolve_outline_content_focus(req)
    metrics_req = "是" if req.require_metrics else "否"
    mode_guidance = {
        "topic": "输入为主题，请围绕该主题补全完整汇报逻辑，不要套用任何默认项目案例。",
        "document": "输入来自文档，请优先提炼文档中的术语、结构与事实，不要替换成与文档无关的其他项目背景。",
        "longText": "输入为长文本，请完整吸收原文信息后再重组为适合演示的章节结构，不要只做简略摘要。",
    }.get(req.input_mode, "请围绕业务输入组织完整、具体的大纲。")
    return "\n".join(
        [
            "你是一名资深 PPT 策划顾问。",
            "请严格输出 JSON，不要输出除 JSON 外的任何内容。",
            "JSON 结构：",
            '{"title":"", "subtitle":"", "slides":[{"title":"","points":[""],"notes":""}]}',
            f"目标页数：{req.n_slides} 页",
            f"语言：{req.language}",
            f"内容导向：{focus_config.get('label')}",
            f"输入模式：{req.input_mode}",
            f"是否强调指标：{metrics_req}",
            mode_guidance,
            *[str(line).strip() for line in focus_config.get("prompt_lines") or [] if str(line).strip()],
            "内容边界：除非业务输入明确提到，否则不要默认引入 Enterprise Intelligent Office Agent、进出口企业协同办公、会议纪要、OCR、审单、数据库、数据决策等特定项目背景。",
            "输出要求：每页必须包含标题、4-6 条具体要点、1 条讲解备注。",
            "标题要求：优先写成结论式、动作式或概括式短句，适合直接作为 PPT 页标题展示。",
            "要点要求：每条要点尽量具体，包含定义、现状、原因、影响、对策、指标、案例、结论中的一种或多种，不要只写空泛短句。",
            "备注要求：可补充该页适合展开的数据、案例、图表建议、发言顺序或解释口径。",
            "演示节奏：整体尽量遵循开场说明、分析展开、方案建议、结尾收束的推进顺序，让目录和页间逻辑更连贯。",
            f"结构建议：优先围绕这些章节组织内容：{'、'.join(str(item) for item in focus_config.get('sections') or [])}。可根据用户主题微调，但不要偏离该内容导向。",
            "如果输入信息较少，也要先补全一版可编辑的完整汇报骨架，避免每页内容过短。",
            "业务输入：",
            input_text,
        ]
    )


def _ensure_template_registry_file() -> None:
    if TEMPLATE_REGISTRY_FILE.exists():
        return
    TEMPLATE_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_REGISTRY_FILE.write_text("[]", encoding="utf-8")


def _load_template_registry() -> List[Dict[str, Any]]:
    _ensure_template_registry_file()
    with _TEMPLATE_REGISTRY_LOCK:
        try:
            data = json.loads(TEMPLATE_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = []
    return data if isinstance(data, list) else []


def _save_template_registry(entries: List[Dict[str, Any]]) -> None:
    _ensure_template_registry_file()
    safe_entries = entries if isinstance(entries, list) else []
    with _TEMPLATE_REGISTRY_LOCK:
        TEMPLATE_REGISTRY_FILE.write_text(
            json.dumps(safe_entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_template_item(item: Dict[str, Any]) -> Dict[str, Any]:
    template_id = str(item.get("template_id") or item.get("id") or item.get("presentation_id") or "").strip()
    if not template_id:
        return {}
    return {
        "template_id": template_id,
        "name": str(item.get("name") or item.get("template_name") or template_id).strip()[:120],
        "description": str(item.get("description") or item.get("summary") or "").strip()[:300],
        "thumbnail_url": str(item.get("thumbnail_url") or item.get("thumbnail") or item.get("cover_url") or "").strip(),
        "source": str(item.get("source") or "presenton").strip(),
        "created_at": str(item.get("created_at") or "").strip(),
        "updated_at": str(item.get("updated_at") or "").strip(),
    }


def _apply_builtin_template_catalog_defaults(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized_item = _normalize_template_item(item) if item and not item.get("template_id") else dict(item or {})
    template_id = str(normalized_item.get("template_id") or "").strip()
    if not template_id:
        return normalized_item
    builtin_defaults = BUILTIN_TEMPLATE_CATALOG_LOOKUP.get(template_id)
    if not builtin_defaults:
        return normalized_item
    normalized_item["name"] = str(builtin_defaults.get("name") or normalized_item.get("name") or template_id).strip()[:120]
    normalized_item["description"] = str(
        builtin_defaults.get("description") or normalized_item.get("description") or ""
    ).strip()[:300]
    if not str(normalized_item.get("source") or "").strip():
        normalized_item["source"] = str(builtin_defaults.get("source") or "builtin")
    return normalized_item


def _extract_template_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    candidates: List[Any] = []
    for key in ("data", "templates", "items", "list", "result", "presentations"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates = value
            break
        if isinstance(value, dict):
            nested_list = value.get("items") or value.get("list")
            if isinstance(nested_list, list):
                candidates = nested_list
                break

    if not candidates and isinstance(payload.get("id"), (str, int)):
        candidates = [payload]

    normalized: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        normalized_item: Dict[str, Any] = {}
        template_field = item.get("template")
        if isinstance(template_field, dict):
            template_payload = dict(template_field)
            template_payload.setdefault(
                "template_id",
                template_payload.get("template_id") or template_payload.get("id") or item.get("presentation_id"),
            )
            if not template_payload.get("description") and item.get("layout_count") is not None:
                template_payload["description"] = f"Custom template · {item.get('layout_count')} layouts"
            template_payload.setdefault("source", "presenton_custom")
            normalized_item = _normalize_template_item(template_payload)

        if not normalized_item:
            normalized_item = _normalize_template_item(item)

        if not normalized_item and item.get("presentation_id"):
            normalized_item = _normalize_template_item(
                {
                    "template_id": item.get("presentation_id"),
                    "name": item.get("name") or item.get("presentation_id"),
                    "description": f"Custom template · {item.get('layout_count', 0)} layouts",
                    "source": "presenton_custom",
                    "updated_at": item.get("last_updated_at") or item.get("updated_at") or "",
                }
            )
        if normalized_item:
            normalized.append(normalized_item)
    return normalized


def _fetch_template_list_from_presenton(base_url: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    errors: List[str] = []
    merged: Dict[str, Dict[str, Any]] = {}
    for path in TEMPLATE_LIST_PATHS:
        try:
            payload = _request_json("GET", f"{base_url}{path}", headers, payload=None, timeout=max(REQUEST_TIMEOUT_SEC, 20))
            items = _extract_template_items(payload)
            for item in items:
                template_id = str(item.get("template_id") or "").strip()
                if not template_id:
                    continue
                previous = merged.get(template_id, {})
                merged[template_id] = {
                    "template_id": template_id,
                    "name": str(item.get("name") or previous.get("name") or template_id),
                    "description": str(item.get("description") or previous.get("description") or ""),
                    "thumbnail_url": str(item.get("thumbnail_url") or previous.get("thumbnail_url") or ""),
                    "source": str(item.get("source") or previous.get("source") or "presenton"),
                    "created_at": str(item.get("created_at") or previous.get("created_at") or ""),
                    "updated_at": str(item.get("updated_at") or previous.get("updated_at") or ""),
                }
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue
    if merged:
        return list(merged.values())
    if errors:
        logger.warning("Template list fetch failed: %s", " | ".join(errors))
    return []


def _fetch_template_detail_from_presenton(base_url: str, headers: Dict[str, str], template_id: str) -> Dict[str, Any]:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    errors: List[str] = []
    for path in TEMPLATE_DETAIL_PATHS:
        resolved = path.replace("{template_id}", requests.utils.quote(clean_id, safe=""))
        try:
            payload = _request_json("GET", f"{base_url}{resolved}", headers, payload=None, timeout=max(REQUEST_TIMEOUT_SEC, 20))
            items = _extract_template_items(payload)
            if items:
                return items[0]
            if isinstance(payload, dict):
                normalized = _normalize_template_item(payload)
                if normalized:
                    return normalized
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue

    # v1 may not expose detail endpoint for built-in templates; fallback to list scan.
    template_list = _fetch_template_list_from_presenton(base_url, headers)
    for item in template_list:
        if str(item.get("template_id")) == clean_id:
            return item

    detail = errors[-1] if errors else "Template not found"
    raise HTTPException(status_code=404, detail=detail)


def _build_generation_payload(req: PresentonGenerateRequest) -> Dict[str, Any]:
    resolved_image_type = _normalize_requested_image_type(req.image_type)
    images_enabled = _images_enabled(req)

    prompt_text = str(req.prompt or "").strip()

    payload: Dict[str, Any] = {
        "prompt": prompt_text,
        "content": prompt_text,
        "instructions": prompt_text,
        "n_slides": req.n_slides,
        "language": req.language,
        "template": req.template,
        "export_as": req.export_as,
        "tone": req.tone,
        "verbosity": req.verbosity,
    }

    if not images_enabled:
        payload["image_type"] = "none"
        payload["web_search"] = False
        payload["include_images"] = False
        payload["enable_images"] = False
        payload["disable_image_generation"] = True
        payload["image_provider"] = "none"
    elif resolved_image_type:
        payload["image_type"] = resolved_image_type

    if req.content_generation:
        payload["content_generation"] = req.content_generation
    if req.markdown_emphasis:
        payload["markdown_emphasis"] = req.markdown_emphasis
    if req.web_search is not None and images_enabled:
        payload["web_search"] = bool(req.web_search)
    if req.include_table_of_contents is not None:
        payload["include_table_of_contents"] = bool(req.include_table_of_contents)
    if req.include_title_slide is not None:
        payload["include_title_slide"] = bool(req.include_title_slide)
    if req.allow_access_to_user_info is not None:
        payload["allow_access_to_user_info"] = bool(req.allow_access_to_user_info)
    if req.trigger_webhook is not None:
        payload["trigger_webhook"] = bool(req.trigger_webhook)
    if isinstance(req.slides_markdown, list) and req.slides_markdown:
        payload["slides_markdown"] = req.slides_markdown
    if isinstance(req.slides_layout, list) and req.slides_layout:
        payload["slides_layout"] = req.slides_layout
    if isinstance(req.files, list) and req.files:
        payload["files"] = [str(item).strip() for item in req.files if str(item).strip()]
    return payload


def _request_generation_with_no_image_fallback(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float = REQUEST_TIMEOUT_SEC,
) -> Dict[str, Any]:
    template_candidates = _template_retry_candidates(payload.get("template"))
    collected_errors: List[str] = []

    for idx, candidate in enumerate(template_candidates):
        candidate_payload = dict(payload)
        candidate_payload["template"] = candidate
        try:
            data = _request_json(method, url, headers, candidate_payload, timeout=timeout)
            original_template = str(payload.get("template") or "").strip()
            if original_template and candidate != original_template:
                logger.warning("Template fallback applied: requested=%s, used=%s", original_template, candidate)
            return data
        except HTTPException as exc:
            detail_text = str(exc.detail or "")
            detail_l = detail_text.lower()

            if str(candidate_payload.get("image_type") or "").lower() == "none" and any(
                token in detail_l for token in ("image_type", "validation", "extra", "unprocessable")
            ):
                fallback_payload = dict(candidate_payload)
                # Keep hard no-image intent and only trim extra compatibility fields.
                for key in ("include_images", "enable_images", "disable_image_generation", "image_provider"):
                    fallback_payload.pop(key, None)
                fallback_payload["image_type"] = "none"
                fallback_payload["web_search"] = False
                logger.warning(
                    "Retrying generation with minimal no-image fields due upstream validation: %s",
                    exc.detail,
                )
                try:
                    return _request_json(method, url, headers, fallback_payload, timeout=timeout)
                except HTTPException as fallback_exc:
                    detail_text = str(fallback_exc.detail or detail_text)
                    detail_l = detail_text.lower()
                    if any(token in detail_l for token in ("image_type", "image provider", "image_provider")):
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                "Presenton does not accept no-image control fields in current endpoint; "
                                "request is blocked to prevent unexpected auto image generation. "
                                f"Upstream detail: {detail_text}"
                            ),
                        ) from fallback_exc
                    collected_errors.append(f"{candidate}: {detail_text}")
                    if not any(token in detail_l for token in ("template not found", "invalid template", "unknown template")):
                        raise fallback_exc
                    if idx < len(template_candidates) - 1:
                        continue
                    raise fallback_exc

            collected_errors.append(f"{candidate}: {detail_text}")
            if not any(token in detail_l for token in ("template not found", "invalid template", "unknown template")):
                raise
            if idx < len(template_candidates) - 1:
                logger.warning("Template %s rejected, retrying next candidate", candidate)
                continue
            raise

    raise HTTPException(status_code=502, detail="; ".join(collected_errors) if collected_errors else "Generation failed")


def _generate_local(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    url = f"{base_url}{LOCAL_GENERATE_PATH}"
    data = _request_generation_with_no_image_fallback("POST", url, headers, payload)
    download_url, edit_url = _extract_urls(data, base_url)
    return {
        "success": True,
        "provider": "local",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": _extract_task_id(data),
        "raw": data,
    }


def _generate_cloud_sync(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    url = f"{base_url}{CLOUD_SYNC_PATH}"
    data = _request_generation_with_no_image_fallback(
        "POST",
        url,
        headers,
        payload,
        timeout=max(REQUEST_TIMEOUT_SEC, POLL_TIMEOUT_SEC),
    )
    download_url, edit_url = _extract_urls(data, base_url)
    return {
        "success": True,
        "provider": "cloud_sync",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": _extract_task_id(data),
        "raw": data,
    }


def _poll_cloud_status(base_url: str, headers: Dict[str, str], task_id: str) -> Dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SEC

    latest: Dict[str, Any] = {}
    while time.time() < deadline:
        latest = _fetch_cloud_status(base_url, headers, task_id)
        status_value = str(latest.get("status") or "").lower()
        if status_value in {"completed", "done", "success", "succeeded"}:
            return latest
        if status_value in {"failed", "error", "cancelled", "canceled"}:
            detail = latest.get("message") or latest.get("error") or "Presenton task failed"
            raise HTTPException(status_code=502, detail=str(detail))
        time.sleep(max(0.2, POLL_INTERVAL_SEC))

    raise HTTPException(status_code=504, detail="Presenton task polling timeout")


def _fetch_cloud_status(base_url: str, headers: Dict[str, str], task_id: str) -> Dict[str, Any]:
    status_path = STATUS_PATH_TEMPLATE.replace("{task_id}", task_id)
    status_url = f"{base_url}{status_path}"
    return _request_json("GET", status_url, headers, payload=None)


def _generate_cloud_async(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    payload = _build_generation_payload(req)
    submit_url = f"{base_url}{CLOUD_ASYNC_PATH}"
    submit_data = _request_generation_with_no_image_fallback("POST", submit_url, headers, payload)
    task_id = _extract_task_id(submit_data)
    if not task_id:
        raise HTTPException(status_code=502, detail="Presenton did not return task id")

    final_data = _poll_cloud_status(base_url, headers, task_id)
    download_url, edit_url = _extract_urls(final_data, base_url)
    return {
        "success": True,
        "provider": "cloud_async",
        "download_url": download_url,
        "edit_url": edit_url,
        "task_id": task_id,
        "raw": final_data,
    }


def _submit_cloud_async_task(base_url: str, headers: Dict[str, str], req: PresentonGenerateRequest) -> Dict[str, Any]:
    submit_url = f"{base_url}{CLOUD_ASYNC_PATH}"
    submit_data = _request_generation_with_no_image_fallback(
        "POST",
        submit_url,
        headers,
        _build_generation_payload(req),
    )
    task_id = _extract_task_id(submit_data)
    if not task_id:
        raise HTTPException(status_code=502, detail="Presenton did not return task id")

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        _ACTIVE_PPT_TASKS[task_id] = time.time()

    return {
        "success": True,
        "provider": "cloud_async",
        "status": "pending",
        "task_id": task_id,
        "message": submit_data.get("message") or "任务已提交",
        "result_link": build_task_result_link(task_id),
        "raw": submit_data,
    }


def _can_use_ordered_pipeline(req: PresentonGenerateRequest) -> bool:
    return _ordered_pipeline_skip_reason(req) is None


def _estimate_delegated_progress(progress_value: Optional[int], status_value: str, message: str) -> int:
    if status_value in {"completed", "done", "success", "succeeded"}:
        return 100
    upstream_progress = progress_value if progress_value is not None else _estimate_progress(status_value, message)
    upstream_progress = max(0, min(100, int(upstream_progress)))
    if status_value in {"failed", "error", "cancelled", "canceled"}:
        return max(88, upstream_progress)
    message_l = str(message or "").lower()
    if progress_value is None:
        if "稳定生成链路" in message or "handoff" in message_l:
            return 70
        if "选择版式" in message or "layout" in message_l:
            return 76
        if "生成页面" in message or "generating slide" in message_l or "generating slides" in message_l:
            return 82
        if "导出" in message or "export" in message_l:
            return 90
        return 66 if status_value == "pending" else 62
    return min(94, max(68, 58 + round(upstream_progress * 0.32)))


def _handoff_ordered_task_to_cloud_async(
    task_id: str,
    base_url: str,
    headers: Dict[str, str],
    req: PresentonGenerateRequest,
    reason: str,
) -> Dict[str, Any]:
    prefer_no_image = _prefer_no_image(req)
    _mark_ordered_template_cooldown(req.template, prefer_no_image, reason)
    handoff_req = _copy_presenton_request(req, prompt=_build_ordered_runtime_prompt(req))
    submit_data = _submit_cloud_async_task(base_url, headers, handoff_req)
    upstream_task_id = str(submit_data.get("task_id") or "").strip()
    handoff_message = "当前模板兼容处理失败，已切换到稳定生成链路继续生成，预计耗时会更长"
    if reason:
        logger.warning("Ordered task %s handed off to cloud async due to: %s", task_id, reason)
    _upsert_ordered_task(
        task_id,
        success=True,
        provider="ordered_async_fallback",
        status="pending",
        progress=68,
        message=handoff_message,
        error=None,
        delegated_task_id=upstream_task_id,
        delegated_provider="cloud_async",
        base_url=base_url,
        raw={
            "handoff_reason": reason,
            "upstream_submit": submit_data.get("raw"),
        },
    )
    return submit_data


def _run_ordered_presenton_task(task_id: str, base_url: str, req: PresentonGenerateRequest) -> None:
    headers = _build_headers()
    try:
        slide_count = len(req.slides_markdown or [])
        ordered_runtime_prompt = _build_ordered_runtime_prompt(req)
        _upsert_ordered_task(task_id, status="pending", progress=8, message="正在创建演示任务")
        create_payload: Dict[str, Any] = {
            "content": ordered_runtime_prompt,
            "n_slides": slide_count or req.n_slides,
            "language": str(req.language or "Chinese"),
            "tone": str(req.tone or "professional"),
            "verbosity": str(req.verbosity or "standard"),
            "instructions": ordered_runtime_prompt,
            "include_table_of_contents": bool(req.include_table_of_contents),
            "include_title_slide": bool(req.include_title_slide),
                "web_search": False if _prefer_no_image(req) else bool(req.web_search),
        }
        if isinstance(req.files, list) and req.files:
            create_payload["file_paths"] = [str(item).strip() for item in req.files if str(item).strip()]

        create_result = _request_json("POST", f"{base_url}{CREATE_PRESENTATION_PATH}", headers, create_payload)
        presentation_id = str(create_result.get("id") or "").strip()
        if not presentation_id:
            raise HTTPException(status_code=502, detail="Presenton create did not return presentation id")

        _upsert_ordered_task(
            task_id,
            status="pending",
            progress=18,
            message="正在加载模板版式",
            presentation_id=presentation_id,
        )
        template_layout = _fetch_presenton_template_group(base_url, headers, str(req.template or "general"))

        _upsert_ordered_task(task_id, status="pending", progress=28, message="正在整理页级版式结构")
        ordered_layout = _build_ordered_layout_payload(req, template_layout)
        prepare_payload = {
            "presentation_id": presentation_id,
            "outlines": [{"content": str(slide or "").strip()} for slide in (req.slides_markdown or [])],
            "layout": ordered_layout,
            "title": _derive_presentation_title(req),
        }
        _request_json(
            "POST",
            f"{base_url}{PREPARE_PRESENTATION_PATH}",
            headers,
            prepare_payload,
            timeout=max(POLL_TIMEOUT_SEC, REQUEST_TIMEOUT_SEC),
        )

        _upsert_ordered_task(task_id, status="pending", progress=42, message=f"正在生成页面 0/{slide_count}")
        _stream_prepared_presentation(task_id, base_url, headers, presentation_id, slide_count)

        _upsert_ordered_task(task_id, status="pending", progress=94, message="正在导出 PPT")
        export_result = _request_json(
            "POST",
            f"{base_url}{EXPORT_PRESENTATION_PATH}",
            headers,
            {
                "id": presentation_id,
                "export_as": str(req.export_as or "pptx"),
            },
            timeout=max(POLL_TIMEOUT_SEC, REQUEST_TIMEOUT_SEC),
        )
        download_url, edit_url = _extract_urls(export_result, base_url)
        decorated = _decorate_result_urls(
            {
                "success": True,
                "provider": "ordered_async",
                "task_id": task_id,
                "download_url": download_url,
                "edit_url": edit_url,
                "raw": export_result,
            },
            base_url,
        )
        _clear_ordered_template_cooldown(
            req.template,
            _prefer_no_image(req),
        )
        _upsert_ordered_task(
            task_id,
            status="completed",
            progress=100,
            message="PPT 生成完成",
            download_url=decorated.get("download_url"),
            edit_url=decorated.get("edit_url"),
            download_url_raw=decorated.get("download_url_raw"),
            edit_url_raw=decorated.get("edit_url_raw"),
            raw=export_result,
        )
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        try:
            _handoff_ordered_task_to_cloud_async(task_id, base_url, headers, req, str(detail))
            return
        except Exception as fallback_exc:
            fallback_detail = fallback_exc.detail if isinstance(fallback_exc, HTTPException) else str(fallback_exc)
            detail = f"{detail}; fallback submit failed: {fallback_detail}"
        _upsert_ordered_task(
            task_id,
            success=False,
            status="failed",
            message=str(detail),
            error=str(detail),
        )
    finally:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            _ACTIVE_PPT_TASKS.pop(task_id, None)
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(base_url)
                except HTTPException as restore_exc:
                    logger.warning("Failed to restore default runtime after ordered task completion: %s", restore_exc.detail)


def _submit_ordered_presenton_task(base_url: str, req: PresentonGenerateRequest) -> Dict[str, Any]:
    task_id = f"ordered-{uuid.uuid4().hex}"
    _upsert_ordered_task(
        task_id,
        status="pending",
        progress=4,
        message="已提交本地加速生成任务",
        base_url=base_url,
    )
    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        _activate_ppt_runtime(base_url)
        _ACTIVE_PPT_TASKS[task_id] = time.time()

    worker = threading.Thread(
        target=_run_ordered_presenton_task,
        args=(task_id, base_url, req),
        daemon=True,
        name=f"presenton-ordered-{task_id[:12]}",
    )
    worker.start()
    return {
        "success": True,
        "provider": "ordered_async",
        "status": "pending",
        "task_id": task_id,
        "message": "任务已提交，正在按已选模板直接生成",
        "result_link": build_task_result_link(task_id),
    }


@router.post("/presenton/outline/generate")
def generate_presenton_outline(req: PresentonOutlineRequest):
    slide_count = max(3, min(40, int(req.n_slides or 8)))
    raw_input = str(req.analysis_input or "").strip()
    doc_name = str(req.document_name or "").strip()
    focus_config = _resolve_outline_content_focus(req)

    if req.input_mode == "topic" and not raw_input:
        raise HTTPException(status_code=400, detail="请先输入 PPT 主题")
    if req.input_mode == "document" and not raw_input and not doc_name:
        raise HTTPException(status_code=400, detail="请先上传文档或补充文档说明")
    if req.input_mode == "longText" and not raw_input:
        raise HTTPException(status_code=400, detail="请先输入或粘贴正文内容")

    input_parts: List[str] = []
    if doc_name:
        input_parts.append(f"文档名称：{doc_name}")
    if raw_input:
        input_parts.append(raw_input)
    if not input_parts:
        input_parts.append("请根据当前主题生成完整且可编辑的汇报大纲。")
    input_text = "\n".join(input_parts)

    fallback_outline = _fallback_outline(req, input_text)
    prompt = _build_outline_prompt(req, input_text)
    llm_raw, llm_issue = _invoke_outline_llm(prompt, req.model_backend)
    parsed = _extract_markdown_json(llm_raw)
    outline = _normalize_outline_payload(parsed, fallback_outline)
    fallback_reason: Optional[str] = llm_issue
    if not fallback_reason and not parsed:
        fallback_reason = "invalid_model_output" if llm_raw else "empty_model_output"
    if not fallback_reason and outline == fallback_outline:
        fallback_reason = "model_output_unusable"

    return {
        "success": True,
        "outline": {
            "title": outline["title"],
            "subtitle": outline.get("subtitle") or _build_outline_subtitle(req, focus_config),
            "slides": outline["slides"][:slide_count],
            "language": req.language,
            "content_focus": next((key for key, item in OUTLINE_CONTENT_FOCUS_CONFIG.items() if item is focus_config), req.content_focus),
            "analysis_framework": str(focus_config.get("label") or ""),
        },
        "meta": {
            "used_fallback": bool(fallback_reason),
            "fallback_reason": fallback_reason,
        },
        "raw_model_output": llm_raw[:6000] if llm_raw else "",
    }


@router.get("/presenton/template/catalog")
def get_presenton_template_catalog(base_url: Optional[str] = None):
    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    remote_items = _fetch_template_list_from_presenton(resolved_base_url, headers)
    imported_items = _load_template_registry()

    merged: Dict[str, Dict[str, Any]] = {}
    for source_items in (BUILTIN_TEMPLATE_CATALOG, remote_items, imported_items):
        for raw_item in source_items:
            item = _normalize_template_item(raw_item) if not raw_item.get("template_id") else raw_item
            template_id = str(item.get("template_id") or "").strip()
            if not template_id:
                continue
            prev = merged.get(template_id, {})
            merged[template_id] = {
                "template_id": template_id,
                "name": str(item.get("name") or prev.get("name") or template_id),
                "description": str(item.get("description") or prev.get("description") or ""),
                "thumbnail_url": str(item.get("thumbnail_url") or prev.get("thumbnail_url") or ""),
                "source": str(item.get("source") or prev.get("source") or "presenton"),
                "created_at": str(item.get("created_at") or prev.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or prev.get("updated_at") or ""),
                "imported": bool(item.get("imported") or prev.get("imported") or False),
            }

    data = [_apply_builtin_template_catalog_defaults(item) for item in merged.values()]

    def _catalog_sort_key(item: Dict[str, Any]) -> Tuple[int, int, str]:
        template_id = str(item.get("template_id") or "").strip()
        if template_id in BUILTIN_TEMPLATE_CATALOG_ORDER:
            return (0, BUILTIN_TEMPLATE_CATALOG_ORDER[template_id], "")
        if bool(item.get("imported")):
            return (1, 0, str(item.get("name") or "").lower())
        return (2, 0, str(item.get("name") or "").lower())

    data.sort(key=_catalog_sort_key)
    return {"success": True, "data": data}


@router.get("/presenton/template/imported")
def list_imported_presenton_templates(
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    _ = ctx
    return {"success": True, "data": _load_template_registry()}


@router.post("/presenton/template/import")
def import_presenton_template(
    payload: PresentonTemplateImportRequest,
    base_url: Optional[str] = None,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    template_id = str(payload.template_id or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    detail = _fetch_template_detail_from_presenton(resolved_base_url, headers, template_id)
    now = datetime.now(timezone.utc).isoformat()
    imported = {
        "template_id": template_id,
        "name": str(payload.alias or detail.get("name") or template_id).strip()[:120],
        "description": str(payload.description or detail.get("description") or "").strip()[:300],
        "thumbnail_url": str(detail.get("thumbnail_url") or "").strip(),
        "source": "presenton_import",
        "imported": True,
        "created_at": now,
        "updated_at": now,
    }

    entries = _load_template_registry()
    updated_entries: List[Dict[str, Any]] = []
    replaced = False
    for item in entries:
        if str(item.get("template_id") or "").strip() == template_id:
            merged_item = dict(item)
            merged_item.update(imported)
            merged_item["created_at"] = item.get("created_at") or now
            updated_entries.append(merged_item)
            replaced = True
        else:
            updated_entries.append(item)
    if not replaced:
        updated_entries.append(imported)

    _save_template_registry(updated_entries)
    logger.info("Admin %s imported template %s", ctx.get("user_id"), template_id)
    return {"success": True, "data": imported}


@router.delete("/presenton/template/import/{template_id}")
def delete_imported_presenton_template(
    template_id: str,
    ctx: Dict[str, Any] = Depends(require_role([ROLE_ADMIN])),
):
    clean_id = str(template_id or "").strip()
    entries = _load_template_registry()
    remained = [item for item in entries if str(item.get("template_id") or "").strip() != clean_id]
    if len(remained) == len(entries):
        raise HTTPException(status_code=404, detail="Template not found in imported list")
    _save_template_registry(remained)
    logger.info("Admin %s removed imported template %s", ctx.get("user_id"), clean_id)
    return {"success": True}


@router.post("/presenton/generate")
def generate_presenton_ppt(req: PresentonGenerateRequest):
    base_url = _normalize_base_url(req.base_url)
    headers = _build_headers()

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        _activate_ppt_runtime(base_url)

    try:
        runner_map = {
            "local": _generate_local,
            "cloud_sync": _generate_cloud_sync,
            "cloud_async": _generate_cloud_async,
        }
        ordered_providers: List[str]
        if req.provider == "auto":
            # Presenton self-host commonly exposes `generate` and `generate/async`.
            ordered_providers = ["local", "cloud_async", "cloud_sync"]
        else:
            ordered_providers = [req.provider]

        errors: List[str] = []
        for provider in ordered_providers:
            runner = runner_map[provider]
            try:
                result = runner(base_url, headers, req)
                return _decorate_result_urls(result, base_url)
            except HTTPException as exc:
                errors.append(f"{provider}: {exc.detail}")
                if req.provider != "auto":
                    raise
                continue
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                if req.provider != "auto":
                    raise HTTPException(status_code=500, detail=str(exc)) from exc
                continue

        raise HTTPException(status_code=502, detail="; ".join(errors) if errors else "Presenton generation failed")
    finally:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(base_url)
                except HTTPException as exc:
                    logger.warning("Failed to restore default model runtime after sync generation: %s", exc.detail)


@router.post("/presenton/generate/async")
def submit_presenton_ppt_task(req: PresentonGenerateRequest):
    base_url = _normalize_base_url(req.base_url)
    headers = _build_headers()
    _purge_stale_ordered_tasks()
    _purge_stale_ordered_template_cooldowns()
    skip_reason = _ordered_pipeline_skip_reason(req)

    if skip_reason is None:
        try:
            result = _submit_ordered_presenton_task(base_url, req)
            _sync_presenton_task_registry(
                str(result.get("task_id") or "").strip(),
                req=req,
                status=result.get("status"),
                progress=4,
                message=result.get("message"),
                provider=result.get("provider"),
                raw=result.get("raw"),
            )
            return result
        except HTTPException as exc:
            logger.warning("Ordered Presenton pipeline unavailable, fallback to upstream async: %s", exc.detail)
        except Exception as exc:
            logger.warning("Ordered Presenton pipeline failed before submit, fallback to upstream async: %s", exc)
    elif isinstance(req.slides_markdown, list) and req.slides_markdown:
        logger.info("Ordered pipeline skipped for template=%s due to %s", req.template, skip_reason)

    try:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            _activate_ppt_runtime(base_url)

        result = _submit_cloud_async_task(base_url, headers, req)
        if skip_reason and skip_reason.startswith("recent_failure:"):
            result["message"] = "当前模板近期在快速生成链路上不稳定，已直接使用稳定生成链路"
            raw_payload = dict(result.get("raw") or {})
            raw_payload["ordered_skip_reason"] = skip_reason
            result["raw"] = raw_payload
        elif skip_reason == "compatibility_policy":
            result["message"] = "当前模板使用稳定生成链路"
        _sync_presenton_task_registry(
            str(result.get("task_id") or "").strip(),
            req=req,
            status=result.get("status"),
            progress=8,
            message=result.get("message"),
            provider=result.get("provider"),
            raw=result.get("raw"),
        )
        return result
    except Exception:
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(base_url)
                except HTTPException as restore_exc:
                    logger.warning("Failed to restore default runtime after async submit failure: %s", restore_exc.detail)
        raise


@router.get("/presenton/generate/status/{task_id}")
def get_presenton_ppt_task_status(task_id: str, base_url: Optional[str] = None):
    _purge_stale_ordered_tasks()
    local_task = _get_ordered_task(task_id)
    if local_task:
        delegated_task_id = str(local_task.get("delegated_task_id") or "").strip()
        if delegated_task_id:
            resolved_base_url = str(local_task.get("base_url") or base_url or "").strip()
            if not resolved_base_url:
                resolved_base_url = _normalize_base_url(base_url)
            headers = _build_headers()
            status_data = _fetch_cloud_status(resolved_base_url, headers, delegated_task_id)
            status_value = _extract_status_value(status_data)
            upstream_message = _extract_status_message(status_data)
            local_message = _translate_progress_message(str(local_task.get("message") or ""))
            display_message = _translate_progress_message(upstream_message or local_message)
            if (
                str(local_task.get("provider") or "") == "ordered_async_fallback"
                and status_value not in TERMINAL_TASK_STATUSES
            ):
                if upstream_message:
                    display_message = f"{_translate_progress_message(upstream_message)}（已切换兼容生成链路）"
                else:
                    display_message = local_message or "已切换兼容生成链路，正在继续生成"
            download_url, edit_url = _extract_urls(status_data, resolved_base_url)
            proxied_download = _build_download_proxy_url(download_url)
            proxied_edit = _build_presenton_proxy_url(edit_url, resolved_base_url)
            explicit_progress = _extract_progress_from_payload(status_data)
            delegated_progress = _estimate_delegated_progress(explicit_progress, status_value, display_message)
            success_value = status_value not in {"failed", "error", "cancelled", "canceled"}

            _upsert_ordered_task(
                task_id,
                success=success_value,
                status=status_value,
                progress=delegated_progress,
                message=display_message,
                download_url=proxied_download or download_url,
                download_url_raw=download_url,
                edit_url=proxied_edit or edit_url,
                edit_url_raw=edit_url,
                error=status_data.get("error") if not success_value else None,
                raw=status_data,
            )

            with _MODEL_RUNTIME_LOCK:
                _purge_stale_tasks_locked()
                if status_value in TERMINAL_TASK_STATUSES:
                    _ACTIVE_PPT_TASKS.pop(task_id, None)
                    _ACTIVE_PPT_TASKS.pop(delegated_task_id, None)
                    if not _ACTIVE_PPT_TASKS:
                        try:
                            _restore_default_runtime(resolved_base_url)
                        except HTTPException as exc:
                            logger.warning("Failed to restore default runtime on delegated task completion: %s", exc.detail)
                else:
                    _ACTIVE_PPT_TASKS[task_id] = time.time()
                    _ACTIVE_PPT_TASKS[delegated_task_id] = time.time()

            _sync_presenton_task_registry(
                task_id,
                status=status_value,
                progress=delegated_progress,
                message=display_message,
                error_message=status_data.get("error"),
                download_url=proxied_download or download_url,
                edit_url=proxied_edit or edit_url,
                provider=str(local_task.get("provider") or "ordered_async_fallback"),
                raw=status_data,
            )
            return {
                "success": success_value,
                "provider": str(local_task.get("provider") or "ordered_async_fallback"),
                "task_id": task_id,
                "upstream_task_id": delegated_task_id,
                "status": status_value,
                "message": display_message,
                "progress": delegated_progress,
                "download_url": proxied_download or download_url,
                "download_url_raw": download_url,
                "edit_url": proxied_edit or edit_url,
                "edit_url_raw": edit_url,
                "error": status_data.get("error"),
                "raw": status_data,
            }

        status_value = str(local_task.get("status") or "pending").lower()
        with _MODEL_RUNTIME_LOCK:
            _purge_stale_tasks_locked()
            if status_value in TERMINAL_TASK_STATUSES:
                _ACTIVE_PPT_TASKS.pop(task_id, None)
            else:
                _ACTIVE_PPT_TASKS[task_id] = time.time()
        local_progress = _coerce_progress_value(local_task.get("progress")) or _estimate_progress(
            status_value,
            _translate_progress_message(str(local_task.get("message") or "")),
        )
        _sync_presenton_task_registry(
            task_id,
            status=status_value,
            progress=local_progress,
            message=_translate_progress_message(str(local_task.get("message") or "")),
            error_message=local_task.get("error"),
            download_url=local_task.get("download_url"),
            edit_url=local_task.get("edit_url"),
            provider=str(local_task.get("provider") or "ordered_async"),
            raw=local_task.get("raw"),
        )
        return {
            "success": bool(local_task.get("success", True)),
            "provider": str(local_task.get("provider") or "ordered_async"),
            "task_id": task_id,
            "status": status_value,
            "message": _translate_progress_message(str(local_task.get("message") or "")),
            "progress": local_progress,
            "download_url": local_task.get("download_url"),
            "download_url_raw": local_task.get("download_url_raw"),
            "edit_url": local_task.get("edit_url"),
            "edit_url_raw": local_task.get("edit_url_raw"),
            "error": local_task.get("error"),
            "raw": local_task.get("raw"),
        }

    resolved_base_url = _normalize_base_url(base_url)
    headers = _build_headers()
    status_data = _fetch_cloud_status(resolved_base_url, headers, task_id)
    status_value = _extract_status_value(status_data)
    message = _translate_progress_message(_extract_status_message(status_data))
    download_url, edit_url = _extract_urls(status_data, resolved_base_url)
    proxied_download = _build_download_proxy_url(download_url)
    proxied_edit = _build_presenton_proxy_url(edit_url, resolved_base_url)
    explicit_progress = _extract_progress_from_payload(status_data)

    with _MODEL_RUNTIME_LOCK:
        _purge_stale_tasks_locked()
        if status_value in TERMINAL_TASK_STATUSES:
            _ACTIVE_PPT_TASKS.pop(task_id, None)
            if status_value in {"failed", "error", "cancelled", "canceled"}:
                logger.warning(
                    "Presenton task %s finished with status=%s message=%s raw_error=%s",
                    task_id,
                    status_value,
                    message,
                    status_data.get("error"),
                )
            if not _ACTIVE_PPT_TASKS:
                try:
                    _restore_default_runtime(resolved_base_url)
                except HTTPException as exc:
                    logger.warning("Failed to restore default runtime on task completion: %s", exc.detail)
        else:
            # Do not mutate runtime during polling; toggling global config mid-task can break Presenton jobs.
            _ACTIVE_PPT_TASKS[task_id] = time.time()

    resolved_progress = explicit_progress if explicit_progress is not None else _estimate_progress(status_value, message)
    _sync_presenton_task_registry(
        task_id,
        status=status_value,
        progress=resolved_progress,
        message=message,
        error_message=status_data.get("error"),
        download_url=proxied_download or download_url,
        edit_url=proxied_edit or edit_url,
        provider="cloud_async",
        raw=status_data,
    )
    return {
        "success": True,
        "provider": "cloud_async",
        "task_id": task_id,
        "status": status_value,
        "message": message,
        "progress": resolved_progress,
        "download_url": proxied_download or download_url,
        "download_url_raw": download_url,
        "edit_url": proxied_edit or edit_url,
        "edit_url_raw": edit_url,
        "raw": status_data,
    }


def refresh_presenton_task_record(task_id: str) -> Optional[Dict[str, Any]]:
    task = get_registered_task(task_id)
    if not task:
        return None
    status_value = str(task.get("status") or "").strip().lower()
    if status_value in TERMINAL_TASK_STATUSES:
        return task
    source_payload = dict(task.get("source_payload") or {})
    base_url = source_payload.get("base_url")
    get_presenton_ppt_task_status(task_id, base_url=base_url)
    return get_registered_task(task_id)


def retry_presenton_task(task_id: str) -> Dict[str, Any]:
    task = get_registered_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    source_payload = dict(task.get("source_payload") or {})
    if not source_payload:
        raise HTTPException(status_code=400, detail="Missing task payload")
    try:
        req = PresentonGenerateRequest(**source_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid task payload: {exc}") from exc
    return submit_presenton_ppt_task(req)


@router.get("/presenton/download")
def proxy_presenton_download(
    target: str,
    base_url: Optional[str] = None,
):
    resolved_base_url = _normalize_base_url(base_url)
    decoded_target = unquote(str(target or "").strip())
    if not decoded_target:
        raise HTTPException(status_code=400, detail="Invalid download target")
    normalized_target = _join_url(resolved_base_url, decoded_target)
    if not normalized_target:
        raise HTTPException(status_code=400, detail="Invalid download target")
    if not _is_same_origin(normalized_target, resolved_base_url):
        raise HTTPException(status_code=400, detail="Download target origin is not allowed")

    headers: Dict[str, str] = {}
    if DEFAULT_PRESENTON_API_KEY:
        headers["Authorization"] = f"Bearer {DEFAULT_PRESENTON_API_KEY}"

    try:
        upstream = _PRESENTON_SESSION.get(normalized_target, headers=headers, timeout=max(REQUEST_TIMEOUT_SEC, 120))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Download proxy failed: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Presenton download failed ({upstream.status_code})")

    parsed = urlparse(normalized_target)
    filename = os.path.basename(parsed.path) or "presentation.pptx"
    content_type = upstream.headers.get(
        "content-type",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    headers_out = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=upstream.content, media_type=content_type, headers=headers_out)


@router.get("/presenton/embed")
def render_presenton_embed(
    target: str,
):
    decoded_target = unquote(str(target or "").strip())
    if not decoded_target.startswith(PRESENTON_PROXY_PREFIX):
        raise HTTPException(status_code=400, detail="Invalid embed target")

    safe_target = json.dumps(decoded_target, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Presenton Embed</title>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #f8fafc;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    .shell {{
      position: relative;
      width: 100%;
      height: 100%;
      background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    }}
    .frame {{
      width: 100%;
      height: 100%;
      border: 0;
      background: #ffffff;
    }}
    .loading {{
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(180deg, rgba(248,250,252,0.96) 0%, rgba(238,242,255,0.92) 100%);
      color: #334155;
      letter-spacing: 0.02em;
      transition: opacity 180ms ease;
      z-index: 1;
    }}
    .loading.hidden {{
      opacity: 0;
      pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="loading" id="loading">正在加载在线编辑器...</div>
    <iframe class="frame" id="frame" src={safe_target} title="Presenton Embed"></iframe>
  </div>
  <script>
    (function() {{
      const frame = document.getElementById('frame');
      const loading = document.getElementById('loading');
      const hideLoading = () => loading.classList.add('hidden');
      frame.addEventListener('load', () => {{
        window.setTimeout(hideLoading, 300);
      }});
      window.setTimeout(hideLoading, 8000);
    }})();
  </script>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.api_route("/presenton/proxy/{proxy_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_presenton_path(
    proxy_path: str,
    request: Request,
    base_url: Optional[str] = None,
):
    resolved_base_url = _normalize_base_url(base_url)
    normalized_path = f"/{(proxy_path or '').lstrip('/')}"
    upstream_url = f"{resolved_base_url}{normalized_path}"
    query = request.url.query
    if query:
        upstream_url = f"{upstream_url}?{query}"

    headers = _build_proxy_upstream_headers(request)
    body = await request.body()
    payload = body if body else None
    expects_event_stream = "text/event-stream" in str(request.headers.get("accept") or "").lower()

    try:
        upstream = _PRESENTON_SESSION.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            data=payload,
            timeout=(10, max(REQUEST_TIMEOUT_SEC, 120)) if expects_event_stream else max(REQUEST_TIMEOUT_SEC, 120),
            stream=expects_event_stream,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Presenton proxy failed: {exc}") from exc

    upstream_headers = _filter_proxy_response_headers(dict(upstream.headers), resolved_base_url)
    content_type = upstream.headers.get("content-type", "")

    if "text/event-stream" in content_type.lower():
        def stream_content():
            try:
                # SSE needs the first bytes to reach the browser immediately; large chunk sizes can stall forever.
                for chunk in upstream.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        stream_headers = {key: value for key, value in upstream_headers.items() if str(key).lower() != "content-type"}
        stream_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        stream_headers["X-Accel-Buffering"] = "no"
        return StreamingResponse(
            stream_content(),
            status_code=upstream.status_code,
            headers=stream_headers,
            media_type=content_type.split(";", 1)[0].strip() or "text/event-stream",
        )

    content = upstream.content

    if any(token in content_type.lower() for token in PROXY_REWRITE_CONTENT_TYPES):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="ignore")
        rewritten = _rewrite_presenton_text_payload(text, resolved_base_url, content_type)
        if "text/html" in content_type.lower():
            rewritten = _inject_presenton_proxy_bootstrap_script(rewritten)
            if "/template-preview" in normalized_path.lower():
                rewritten = _inject_template_preview_i18n_script(rewritten)
        content = rewritten.encode("utf-8")
        if content_type:
            base_mime = content_type.split(";")[0].strip()
            upstream_headers["Content-Type"] = f"{base_mime}; charset=utf-8"

    if "/template-preview" in normalized_path.lower() or "/_next/" in normalized_path.lower():
        upstream_headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        upstream_headers["Pragma"] = "no-cache"

    return Response(content=content, status_code=upstream.status_code, headers=upstream_headers)
