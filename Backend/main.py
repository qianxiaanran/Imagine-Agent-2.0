import os
import sys
import time
import threading
import uuid
import gzip
from datetime import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

try:
    import brotli
except Exception:
    brotli = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

_env_dir = os.path.dirname(__file__)
load_dotenv(dotenv_path=os.path.join(_env_dir, ".env"), override=False)
load_dotenv(dotenv_path=os.path.join(_env_dir, ".env.local"), override=True)
from runtime_storage import (
    RUNTIME_OCR_ROOT,
    RUNTIME_STATIC_ROOT,
    build_static_api_url,
    cleanup_runtime_files,
    ensure_runtime_layout,
    migrate_legacy_runtime_files,
    start_runtime_cleanup_loop,
)

ensure_runtime_layout()
migrate_legacy_runtime_files()

# 初始化可选模块
auth_router = None
user_router = None
chat_router = None
audit_router = None
admin_router = None
decision_router = None
presentation_router = None
warmup_decision_cache = None
upload_document_to_vector_store = None
delete_user_documents = None
store_text_to_vector_store = None
submit_document_upload_task = None
get_document_upload_task = None
submit_file_task = None
get_task_result = None
submit_supabase_task = None
get_file_signed_url = None
upload_bytes_to_supabase = None
OCRManager = None
get_shared_ocr_manager = None
ocr_agent = None
save_context = None
voice_ws_proxy = None
generate_report_outline = None
generate_email_draft = None
parse_ocr_content = None
save_ocr_record = None
warmup_embeddings = None
# 添加了可选的同步 ASR 可调用功能
baidu_asr_from_bytes = None
get_cached_sms_session = None
_USER_STATUS_CACHE_TTL_SECONDS = max(5.0, float(os.getenv("USER_STATUS_CACHE_TTL_SECONDS", "15")))
_USER_STATUS_CACHE_LOCK = threading.Lock()
_USER_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}
BACKEND_COMPRESSION_ENABLED = os.getenv("BACKEND_COMPRESSION", "true").lower() != "false"
BACKEND_COMPRESSION_MIN_SIZE = max(256, int(os.getenv("BACKEND_COMPRESSION_MIN_SIZE", "1024")))
BACKEND_GZIP_LEVEL = min(9, max(1, int(os.getenv("BACKEND_GZIP_LEVEL", "5"))))
BACKEND_BROTLI_QUALITY = min(11, max(0, int(os.getenv("BACKEND_BROTLI_QUALITY", "4"))))
COMPRESSIBLE_CONTENT_TYPES = (
    "application/json",
    "application/problem+json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
)


def _save_ocr_upload(content: bytes, filename: str) -> str:
    date_folder = datetime.utcnow().strftime("%Y%m%d")
    ext = os.path.splitext(filename or "")[1]
    if ext and len(ext) > 10:
        ext = ""
    safe_name = f"{uuid.uuid4().hex}{ext}"
    abs_dir = RUNTIME_OCR_ROOT / date_folder
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / safe_name
    with open(abs_path, "wb") as f:
        f.write(content)
    return build_static_api_url("ocr", date_folder, safe_name)


def _merge_vary_header(existing: Optional[str], token: str) -> str:
    current = [item.strip() for item in str(existing or "").split(",") if item.strip()]
    lowered = {item.lower() for item in current}
    if token.lower() not in lowered:
        current.append(token)
    return ", ".join(current)


def _is_compressible_content_type(content_type: str) -> bool:
    normalized = str(content_type or "").split(";", 1)[0].strip().lower()
    if not normalized or normalized == "text/event-stream":
        return False
    if normalized.startswith("text/"):
        return True
    return normalized in COMPRESSIBLE_CONTENT_TYPES


class BackendCompressionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = BACKEND_COMPRESSION_MIN_SIZE,
        gzip_level: int = BACKEND_GZIP_LEVEL,
        brotli_quality: int = BACKEND_BROTLI_QUALITY,
    ) -> None:
        self.app = app
        self.minimum_size = max(0, int(minimum_size))
        self.gzip_level = min(9, max(1, int(gzip_level)))
        self.brotli_quality = min(11, max(0, int(brotli_quality)))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET").upper()
        if path.startswith(("/static", "/api/static")) or method == "HEAD":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        accept_encoding = request_headers.get("accept-encoding", "").lower()
        allow_br = "br" in accept_encoding and brotli is not None
        allow_gzip = "gzip" in accept_encoding
        if not allow_br and not allow_gzip:
            await self.app(scope, receive, send)
            return

        started: Optional[Message] = None
        body_chunks: List[bytes] = []

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = message
                return

            if message["type"] != "http.response.body":
                await send(message)
                return

            body_chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return

            response_start = started or {"type": "http.response.start", "status": 200, "headers": []}
            headers = MutableHeaders(raw=response_start.setdefault("headers", []))
            status_code = int(response_start.get("status", 200))
            body = b"".join(body_chunks)
            headers["Vary"] = _merge_vary_header(headers.get("Vary"), "Accept-Encoding")

            if (
                status_code < 200
                or status_code in (204, 304)
                or headers.get("Content-Encoding")
                or headers.get("Content-Range")
                or headers.get("X-No-Compression") == "1"
                or len(body) < self.minimum_size
                or not _is_compressible_content_type(headers.get("Content-Type", ""))
            ):
                headers["Content-Length"] = str(len(body))
                await send(response_start)
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return

            compressed = body
            encoding = ""
            if allow_br:
                candidate = brotli.compress(body, quality=self.brotli_quality)
                if len(candidate) < len(body):
                    compressed = candidate
                    encoding = "br"

            if not encoding and allow_gzip:
                candidate = gzip.compress(body, compresslevel=self.gzip_level)
                if len(candidate) < len(body):
                    compressed = candidate
                    encoding = "gzip"

            if encoding:
                headers["Content-Encoding"] = encoding
                headers["Content-Length"] = str(len(compressed))
                await send(response_start)
                await send({"type": "http.response.body", "body": compressed, "more_body": False})
                return

            headers["Content-Length"] = str(len(body))
            await send(response_start)
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, send_wrapper)


def _get_cached_user_status_profile(user_id: str) -> Optional[Dict[str, Any]]:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id or "_fetch_profile" not in globals():
        return None

    now = time.time()
    with _USER_STATUS_CACHE_LOCK:
        cached = _USER_STATUS_CACHE.get(normalized_user_id)
        if cached and (now - float(cached.get("fetched_at") or 0.0)) < _USER_STATUS_CACHE_TTL_SECONDS:
            return cached.get("profile")

    profile = _fetch_profile(normalized_user_id)
    with _USER_STATUS_CACHE_LOCK:
        _USER_STATUS_CACHE[normalized_user_id] = {
            "profile": profile,
            "fetched_at": now,
        }
        if len(_USER_STATUS_CACHE) > 512:
            stale_keys = [
                key
                for key, value in _USER_STATUS_CACHE.items()
                if (now - float(value.get("fetched_at") or 0.0)) >= _USER_STATUS_CACHE_TTL_SECONDS
            ]
            for key in stale_keys[:128]:
                _USER_STATUS_CACHE.pop(key, None)
    return profile

try:
    from auth_router import router as auth_router, user_router
    from chat_router import router as chat_router
    from audit_router import router as audit_router
    from admin_router import router as admin_router
    from decision_router import router as decision_router, warmup_decision_cache
    from documents_processing import upload_document_to_vector_store, delete_user_documents, store_text_to_vector_store, warmup_embeddings
    from document_upload_tasks import submit_document_upload_task, get_document_upload_task
    from voice_files_processing import submit_file_task, get_task_result, submit_supabase_task, get_file_signed_url, upload_bytes_to_supabase
    from ocr_manager import OCRManager, get_shared_ocr_manager
    from history_manager import save_context
    import share_manager
    from report_email_manager import generate_report_outline, generate_email_draft
    from ocr_structured import parse_ocr_content, save_ocr_record
    import voice_ws_proxy
    from admin_utils import _bearer_token, _get_token_iat, _get_user_from_token, _fetch_profile
    from auth_router import _get_session_from_token as get_cached_sms_session
    # 导入同步 ASR 助手
    from voice_manager import baidu_asr_from_bytes
    from deepseek_llm import warmup_models

    print("[Init] Modules loaded")
except Exception as e:
    warmup_models = None
    print(f"[ImportError] Failed to import optional modules: {e}")
    import traceback
    traceback.print_exc()

try:
    from presentation_router import router as presentation_router
    print("[Presentation] presentation_router loaded")
except Exception as e:
    presentation_router = None
    print(f"[Presentation] presentation_router unavailable: {e}")

# 单独的负载共享模块
share_manager = None
try:
    import share_manager as _share_manager

    share_manager = _share_manager
    print("[Share] share_manager loaded")
except Exception as e:
    print(f"[Share] share_manager unavailable: {e}")
    import traceback
    traceback.print_exc()

app = FastAPI(title="Enterprise AI API")

if BACKEND_COMPRESSION_ENABLED:
    app.add_middleware(
        BackendCompressionMiddleware,
        minimum_size=BACKEND_COMPRESSION_MIN_SIZE,
        gzip_level=BACKEND_GZIP_LEVEL,
        brotli_quality=BACKEND_BROTLI_QUALITY,
    )

@app.on_event("startup")
def _bootstrap_runtime_storage():
    ensure_runtime_layout()
    migrate_legacy_runtime_files()
    cleanup_runtime_files()
    start_runtime_cleanup_loop()


@app.on_event("startup")
def _warmup_models():
    llm_warmup_enabled = os.getenv("LLM_WARMUP", "true").lower() != "false"
    decision_warmup_enabled = os.getenv("DECISION_WARMUP", "true").lower() != "false"

    if (
        not llm_warmup_enabled
        and not decision_warmup_enabled
    ):
        return
    if not warmup_models and not warmup_embeddings and not warmup_decision_cache:
        return

    def _run_warmups():
        if llm_warmup_enabled and warmup_models:
            warmup_models()
        if llm_warmup_enabled and warmup_embeddings:
            warmup_embeddings()
        if decision_warmup_enabled and warmup_decision_cache:
            warmup_decision_cache()

    threading.Thread(target=_run_warmups, daemon=True).start()


if OCRManager:
    try:
        ocr_agent = get_shared_ocr_manager() if get_shared_ocr_manager else OCRManager()
        print("[OCR] Engine initialized")
    except Exception as e:
        print(f"[OCR] Engine init failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[OCR] module not loaded, skip init")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if "health" not in request.url.path and "result" not in request.url.path:
        print(f"\n[HTTP] {request.method} {request.url.path}")
    start = time.time()
    response = await call_next(request)
    if "health" not in request.url.path and "result" not in request.url.path:
        print(f"[HTTP] done | status {response.status_code} | took {time.time() - start:.2f}s")
    return response


@app.middleware("http")
async def enforce_user_status(request: Request, call_next):
    path = request.url.path
    skip_prefixes = ("/health", "/api/auth", "/api/public", "/api/static", "/static")
    if path.startswith(skip_prefixes):
        return await call_next(request)

    if "_bearer_token" not in globals():
        return await call_next(request)

    token = _bearer_token(request.headers.get("authorization"))
    if token and len(token) > 100:
        try:
            user = _get_user_from_token(token)
            profile = _get_cached_user_status_profile(user.id)
            if profile:
                if profile.get("status") == "disabled":
                    return JSONResponse(status_code=403, content={"detail": "Account disabled"})
                force_logout_at = profile.get("force_logout_at")
                iat = _get_token_iat(token) if "_get_token_iat" in globals() else None
                if force_logout_at and iat:
                    try:
                        logout_ts = datetime.fromisoformat(str(force_logout_at).replace("Z", "+00:00")).timestamp()
                        if iat < int(logout_ts):
                            return JSONResponse(status_code=401, content={"detail": "Session expired"})
                    except Exception:
                        pass
        except Exception:
            pass

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

STATIC_DIR = str(RUNTIME_STATIC_ROOT)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_root")
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static_api")

if auth_router: app.include_router(auth_router)
if user_router: app.include_router(user_router)
if chat_router:
    app.include_router(chat_router)
else:
    print("[Warn] Chat Router not loaded, /api/chat is unavailable")
if audit_router:
    app.include_router(audit_router)
else:
    print("[Warn] Audit Router not loaded, /api/audit endpoints unavailable")
if admin_router:
    app.include_router(admin_router)
else:
    print("[Warn] Admin Router not loaded, /api/admin endpoints unavailable")
if decision_router:
    app.include_router(decision_router)
else:
    print("[Warn] Decision Router not loaded, /api/decision endpoints unavailable")
if presentation_router:
    app.include_router(presentation_router)
else:
    print("[Warn] Presentation Router not loaded, /api/presentation endpoints unavailable")
if voice_ws_proxy: app.include_router(voice_ws_proxy.router, prefix="/api/ws", tags=["Voice WebSocket"])


class ReportRequest(BaseModel):
    topic: str
    scene: str
    audience: str
    length: str
    key_points: str


class EmailRequest(BaseModel):
    subject: str
    receiver_role: str
    scene: str
    key_points: str
    tone: str


class TranscribeRequest(BaseModel):
    file_path: str
    original_name: str


class ContextPayload(BaseModel):
    content: str
    type: Optional[str] = "context_save"


class OCRIngestPayload(BaseModel):
    content: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    title: Optional[str] = None


class OCRParsePayload(BaseModel):
    content: str
    hint_type: Optional[str] = None
    llm_backend: Optional[str] = None
    use_llm: Optional[bool] = True


class OCRSubmitPayload(BaseModel):
    doc_type: str
    fields: dict
    content: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    title: Optional[str] = None


class ShareCreateRequest(BaseModel):
    session_id: str
    title: Optional[str] = None
    days: int = 7
    user_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/share/create")
async def create_share(req: ShareCreateRequest, user_id: Optional[str] = None):
    uid = user_id or req.user_id
    if not uid: return {"success": False, "error": "Missing user_id"}
    if not share_manager: return {"success": False, "error": "Share feature is disabled on server"}
    token = share_manager.create_share_link(uid, req.session_id, req.title, req.days)
    if token: return {"success": True, "token": token}
    detail = ""
    try:
        detail = (share_manager.get_last_error() or "").strip()
    except Exception:
        detail = ""
    return {"success": False, "error": detail or "Failed to create share link"}


@app.get("/api/public/share/{token}")
async def get_share_content(token: str):
    if not share_manager: return {"success": False, "error": "Share feature is disabled on server"}
    result = share_manager.get_shared_content(token)
    if "error" in result:
        detail = str(result["error"] or "").strip()
        if detail == "Internal server error":
            try:
                extra = (share_manager.get_last_error() or "").strip()
                if extra:
                    detail = f"{detail}: {extra}"
            except Exception:
                pass
        return {"success": False, "error": detail}
    return {"success": True, "data": result}


@app.post("/api/history/{session_id}/context")
async def save_session_context(session_id: str, payload: ContextPayload, user_id: str):
    if save_context:
        success = save_context(user_id, session_id, payload.content, func_type=payload.type)
        if success:
            return {"success": True}
        else:
            return {"error": "Failed to save context to database"}
    return {"error": "History Service Unavailable"}


@app.post("/api/ocr/recognize")
async def ocr_recognize(file: UploadFile = File(...), engine: Optional[str] = Form(None)):
    if not ocr_agent:
        return {"error": "OCR service unavailable"}
    try:
        engine_value = (engine or "standard").strip().lower()
        if engine_value not in ("vl", "standard"):
            engine_value = "standard"
        content = await file.read()
        if not content:
            return {"error": "Empty file"}
        file_url = _save_ocr_upload(content, file.filename)
        result = ocr_agent.recognize(content, file.filename, engine=engine_value)
        result["file_url"] = file_url
        result["file_name"] = file.filename
        result["file_type"] = file.content_type or ""
        text_value = str(result.get("text") or "")
        if text_value and not (text_value.startswith("\u274c") or text_value.startswith("[ERROR]")):
            ocr_agent.store(text_value, file.filename)
        return {"success": True, "data": result}
    except Exception as e:
        print(f"[OCR] API error: {e}")
        return {"error": str(e)}


@app.post("/api/ocr/ingest")
async def ocr_ingest(payload: OCRIngestPayload):
    if not store_text_to_vector_store:
        return {"success": False, "error": "Vector store unavailable"}
    content = (payload.content or "").strip()
    if not content:
        return {"success": False, "error": "Empty content"}
    user_id = payload.user_id or "anonymous"
    ok, msg, count = store_text_to_vector_store(
        content,
        user_id=user_id,
        source="ocr",
        title=payload.title,
        session_id=payload.session_id,
    )
    if ok:
        return {"success": True, "count": count}
    return {"success": False, "error": msg}


@app.post("/api/ocr/parse")
async def ocr_parse(payload: OCRParsePayload):
    if not parse_ocr_content:
        return {"success": False, "error": "OCR parse service unavailable"}
    content = (payload.content or "").strip()
    if not content:
        return {"success": False, "error": "Empty content"}
    try:
        result = parse_ocr_content(
            content,
            payload.hint_type,
            payload.llm_backend,
            payload.use_llm if payload.use_llm is not None else True,
        )
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/ocr/submit")
async def ocr_submit(payload: OCRSubmitPayload):
    if not save_ocr_record:
        return {"success": False, "error": "OCR submit service unavailable"}
    if not payload.doc_type:
        return {"success": False, "error": "Missing doc_type"}
    if not isinstance(payload.fields, dict):
        return {"success": False, "error": "Invalid fields payload"}
    try:
        ok, record_id, err = save_ocr_record(
            doc_type=payload.doc_type,
            fields=payload.fields,
            raw_text=payload.content,
            user_id=payload.user_id,
            session_id=payload.session_id,
            title=payload.title,
        )
        if ok:
            return {"success": True, "record_id": record_id}
        return {"success": False, "error": err or "Insert failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    [File mode] upload file -> store -> async transcription (for long recordings)
    """
    if not submit_file_task: return {"error": "Voice Service Unavailable"}
    try:
        task_id = await submit_file_task(file)
        task_info = get_task_result(task_id)
        file_path = task_info.get('file_path')

        if not task_id: return {"error": "File save failed"}
        return {
            "task_id": task_id,
            "message": "Task submitted via direct upload",
            "file_path": file_path
        }
    except Exception as e:
        print(f"[Voice] API error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# 新增：实时语音/短音频端点
@app.post("/api/voice/instant")
async def transcribe_instant(file: UploadFile = File(...)):
    """
    [Realtime mode] upload bytes directly -> return text synchronously (for short recordings)
    """
    if not baidu_asr_from_bytes: return {"error": "Voice Manager Unavailable"}
    try:
        content = await file.read()
        stored_path = None
        if upload_bytes_to_supabase:
            stored_path = await upload_bytes_to_supabase(
                content,
                file.filename,
                file.content_type or "audio/wav"
            )
        # 在 voice_manager 中调用同步 ASR 助手
        text = baidu_asr_from_bytes(content, file.filename)
        return {"success": True, "text": text, "file_path": stored_path}
    except Exception as e:
        print(f"[Voice] realtime API error: {e}")
        return {"error": str(e)}


@app.post("/api/voice/transcribe_supabase")
async def transcribe_via_supabase(req: TranscribeRequest):
    if not submit_supabase_task: return {"error": "Voice Service Unavailable"}
    try:
        task_id = await submit_supabase_task(req.file_path, req.original_name)
        return {"task_id": task_id, "message": "Task submitted via Supabase"}
    except Exception as e:
        print(f"[Voice] Supabase API error: {e}")
        return {"error": str(e)}


@app.get("/api/voice/result/{task_id}")
async def get_transcribe_result_api(task_id: str):
    if not get_task_result: return {"error": "Voice Service Unavailable"}
    return get_task_result(task_id)


@app.get("/api/voice/playback_url")
async def get_audio_playback_url(path: str = Query(..., description="Supabase storage path")):
    if not get_file_signed_url: return {"error": "Service Unavailable"}
    try:
        url = get_file_signed_url(path)
        if url: return {"success": True, "url": url}
        return {"error": "Failed to generate URL"}
    except Exception as e:
        return {"error": str(e)}


# 更新：RAG 上传端点返回预览
@app.post("/api/documents/upload")
async def upload_docs(
    request: Request,
    user_id: Optional[str] = Form(None),
    replace_existing: bool = Form(False),
    files: List[UploadFile] = File(...),
):
    if not submit_document_upload_task:
        return {"error": "Document Service Unavailable"}

    provided_user_id = (user_id or "").strip()
    resolved_user_id = provided_user_id
    token = _bearer_token(request.headers.get("authorization")) if "_bearer_token" in globals() else None
    if token:
        try:
            token_user_id = None
            # 智威汤逊
            if len(token) > 100 and "_get_user_from_token" in globals():
                token_user = _get_user_from_token(token)
                token_user_id = getattr(token_user, "id", None)
            # 短信登录临时令牌
            elif token.startswith("sms-token-") and get_cached_sms_session:
                sms_session = get_cached_sms_session(token)
                if sms_session:
                    token_user_id = sms_session.get("user_id")

            if token_user_id:
                token_user_id = str(token_user_id).strip()
                if provided_user_id and provided_user_id != token_user_id:
                    return JSONResponse(status_code=403, content={"error": "user_id does not match session token"})
                resolved_user_id = token_user_id
            elif not provided_user_id:
                return JSONResponse(status_code=401, content={"error": "Invalid session token"})
        except Exception:
            return JSONResponse(status_code=401, content={"error": "Invalid session token"})

    if not resolved_user_id:
        return JSONResponse(status_code=400, content={"error": "Missing user_id"})

    upload_items: List[Dict[str, Any]] = []
    for f in files:
        try:
            content = await f.read()
            if not content:
                return JSONResponse(status_code=400, content={"error": f"Empty file: {f.filename}"})
            upload_items.append(
                {
                    "filename": f.filename,
                    "content": content,
                    "content_type": f.content_type or "application/octet-stream",
                    "size": len(content),
                }
            )
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Read file failed: {f.filename}: {e}"})

    task = submit_document_upload_task(
        user_id=resolved_user_id,
        files=upload_items,
        replace_existing=replace_existing,
    )
    return {
        "status": "queued",
        "task_id": task.get("task_id"),
        "file_count": len(upload_items),
        "message": "Document upload task submitted",
    }


@app.get("/api/documents/upload/result/{task_id}")
async def get_document_upload_result_api(task_id: str):
    if not get_document_upload_task:
        return {"error": "Document Service Unavailable"}
    return get_document_upload_task(task_id)

@app.post("/api/generate/report")
def api_gen_report(req: ReportRequest):
    if not generate_report_outline: return {"error": "Service Unavailable"}
    return {"success": True,
            "result": generate_report_outline(req.topic, req.scene, req.audience, req.length, req.key_points)}


@app.post("/api/generate/email")
def api_gen_email(req: EmailRequest):
    if not generate_email_draft: return {"error": "Service Unavailable"}
    return {"success": True,
            "result": generate_email_draft(req.subject, req.receiver_role, req.scene, req.key_points, req.tone)}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "18011"))
    print(f"[Server] FastAPI listening on {host}:{port}")
    uvicorn.run(app, host=host, port=port, ws_ping_interval=20, ws_ping_timeout=20)

