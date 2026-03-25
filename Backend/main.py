import os
import sys
import time
import threading
import uuid
import io
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

_env_dir = os.path.dirname(__file__)
load_dotenv(dotenv_path=os.path.join(_env_dir, ".env"), override=False)
load_dotenv(dotenv_path=os.path.join(_env_dir, ".env.local"), override=True)
from runtime_storage import (
    RUNTIME_OCR_ROOT,
    RUNTIME_SEAL_ROOT,
    RUNTIME_STATIC_ROOT,
    build_static_api_url,
    cleanup_runtime_files,
    configure_process_temp_dir,
    ensure_runtime_layout,
    migrate_legacy_runtime_files,
    start_runtime_cleanup_loop,
)

ensure_runtime_layout()
configure_process_temp_dir()
migrate_legacy_runtime_files()

# 初始化可选模块
auth_router = None
user_router = None
chat_router = None
audit_router = None
admin_router = None
tasks_router = None
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
create_instant_task = None
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
register_ocr_task = None
complete_ocr_task = None
fail_ocr_task = None
set_ocr_task_runner = None
extract_transparent_seal = None
# 添加了可选的同步 ASR 可调用功能
baidu_asr_from_bytes = None
get_cached_sms_session = None
_USER_STATUS_CACHE_TTL_SECONDS = max(5.0, float(os.getenv("USER_STATUS_CACHE_TTL_SECONDS", "15")))
_USER_STATUS_CACHE_LOCK = threading.Lock()
_USER_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}


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


def _save_seal_output(content: bytes) -> str:
    return _save_seal_asset(content, "seal.png", default_ext=".png")


def _save_seal_source(content: bytes, filename: str) -> str:
    return _save_seal_asset(content, filename or "seal-source.png", default_ext=".png")


def _save_seal_asset(content: bytes, filename: str, default_ext: str = ".png") -> str:
    date_folder = datetime.utcnow().strftime("%Y%m%d")
    ext = os.path.splitext(filename or "")[1]
    if not ext or len(ext) > 10:
        ext = default_ext
    safe_name = f"{uuid.uuid4().hex}{ext}"
    abs_dir = RUNTIME_SEAL_ROOT / date_folder
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / safe_name
    with open(abs_path, "wb") as f:
        f.write(content)
    return build_static_api_url("ocr", "seal", date_folder, safe_name)


def _save_seal_archive(content: bytes) -> str:
    return _save_seal_asset(content, "seals.zip", default_ext=".zip")


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


def _resolve_request_user_id(
    request: Request,
    provided_user_id: Optional[str] = None,
    *,
    allow_anonymous: bool = True,
) -> Optional[str]:
    resolved_user_id = str(provided_user_id or "").strip()
    token = _bearer_token(request.headers.get("authorization")) if "_bearer_token" in globals() else None
    if token:
        try:
            token_user_id = None
            if len(token) > 100 and "_get_user_from_token" in globals():
                token_user = _get_user_from_token(token)
                token_user_id = getattr(token_user, "id", None)
            elif token.startswith("sms-token-") and get_cached_sms_session:
                sms_session = get_cached_sms_session(token)
                if sms_session:
                    token_user_id = sms_session.get("user_id")

            if token_user_id:
                token_user_id = str(token_user_id).strip()
                if resolved_user_id and resolved_user_id != token_user_id:
                    raise ValueError("user_id does not match session token")
                resolved_user_id = token_user_id
            elif not resolved_user_id and not allow_anonymous:
                raise ValueError("Invalid session token")
        except ValueError:
            raise
        except Exception:
            if not allow_anonymous:
                raise ValueError("Invalid session token")
    if resolved_user_id:
        return resolved_user_id
    return "anonymous" if allow_anonymous else None

try:
    from auth_router import router as auth_router, user_router
    from chat_router import router as chat_router
    from audit_router import router as audit_router
    from admin_router import router as admin_router
    from decision_router import router as decision_router, warmup_decision_cache
    from documents_processing import upload_document_to_vector_store, delete_user_documents, store_text_to_vector_store, warmup_embeddings
    from document_upload_tasks import submit_document_upload_task, get_document_upload_task
    from voice_files_processing import submit_file_task, get_task_result, submit_supabase_task, get_file_signed_url, upload_bytes_to_supabase, create_instant_task
    from ocr_manager import OCRManager, get_shared_ocr_manager
    from ocr_task_manager import register_ocr_task, complete_ocr_task, fail_ocr_task, set_ocr_task_runner
    from history_manager import save_context
    import share_manager
    from report_email_manager import generate_report_outline, generate_email_draft
    from ocr_structured import parse_ocr_content, save_ocr_record
    from seal_extractor import extract_transparent_seal
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

try:
    from tasks_router import router as tasks_router
    print("[Tasks] tasks_router loaded")
except Exception as e:
    tasks_router = None
    print(f"[Tasks] tasks_router unavailable: {e}")

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


def _run_ocr_recognition(content: bytes, filename: str, engine_value: str) -> Dict[str, Any]:
    if not ocr_agent:
        raise RuntimeError("OCR service unavailable")
    result = ocr_agent.recognize(content, filename, engine=engine_value)
    text_value = str(result.get("text") or "")
    if text_value and not (text_value.startswith("\u274c") or text_value.startswith("[ERROR]")):
        ocr_agent.store(text_value, filename)
    return result


if set_ocr_task_runner:
    try:
        set_ocr_task_runner(_run_ocr_recognition)
    except Exception:
        pass


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
if tasks_router:
    app.include_router(tasks_router)
else:
    print("[Warn] Tasks Router not loaded, /api/tasks endpoints unavailable")
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
async def ocr_recognize(
    request: Request,
    file: UploadFile = File(...),
    engine: Optional[str] = Form(None),
):
    if not ocr_agent:
        return {"error": "OCR service unavailable"}
    task_record = None
    try:
        engine_value = (engine or "standard").strip().lower()
        if engine_value not in ("vl", "standard"):
            engine_value = "standard"
        try:
            resolved_user_id = _resolve_request_user_id(request, allow_anonymous=True)
        except ValueError as exc:
            return JSONResponse(status_code=401, content={"error": str(exc)})
        content = await file.read()
        if not content:
            return {"error": "Empty file"}
        file_url = _save_ocr_upload(content, file.filename)
        if register_ocr_task:
            task_record = register_ocr_task(
                file_bytes=content,
                filename=file.filename,
                user_id=resolved_user_id or "anonymous",
                engine=engine_value,
                file_url=file_url,
                file_type=file.content_type or "",
            )
        result = _run_ocr_recognition(content, file.filename, engine_value)
        result["file_url"] = file_url
        result["file_name"] = file.filename
        result["file_type"] = file.content_type or ""
        if complete_ocr_task and isinstance(task_record, dict):
            complete_ocr_task(str(task_record.get("task_id") or ""), result)
        return {
            "success": True,
            "task_id": task_record.get("task_id") if isinstance(task_record, dict) else None,
            "result_link": task_record.get("result_link") if isinstance(task_record, dict) else None,
            "data": result,
        }
    except Exception as e:
        print(f"[OCR] API error: {e}")
        if fail_ocr_task and isinstance(task_record, dict):
            try:
                fail_ocr_task(str(task_record.get("task_id") or ""), str(e))
            except Exception:
                pass
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


@app.post("/api/ocr/seal-extract")
async def ocr_seal_extract(
    request: Request,
    file: UploadFile = File(...),
    target_color: Optional[str] = Form("#d81e2f"),
    tolerance: Optional[int] = Form(30),
    gray_threshold: Optional[float] = Form(0.06),
    channel_mode: Optional[str] = Form("auto"),
    channel_ratio: Optional[int] = Form(38),
    crop_mode: Optional[str] = Form("focus"),
    fill_radius: Optional[int] = Form(10),
    extract_mode: Optional[str] = Form("smart"),
    prefer_paddle: Optional[bool] = Form(True),
):
    if not extract_transparent_seal:
        return JSONResponse(status_code=503, content={"success": False, "error": "Seal extraction service unavailable"})

    try:
        _resolve_request_user_id(request, allow_anonymous=True)
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"success": False, "error": str(exc)})

    try:
        content = await file.read()
        if not content:
            return JSONResponse(status_code=400, content={"success": False, "error": "Empty file"})
        source_url = _save_seal_source(content, file.filename or "seal-source.png")

        settings = {
            "target_color": target_color,
            "tolerance": tolerance,
            "gray_threshold": gray_threshold,
            "channel_mode": channel_mode,
            "channel_ratio": channel_ratio,
            "crop_mode": crop_mode,
            "fill_radius": fill_radius,
            "extract_mode": extract_mode,
            "prefer_paddle": prefer_paddle,
        }

        result = extract_transparent_seal(
            content,
            file.filename or "seal-source",
            settings=settings,
            ocr_engine=ocr_agent,
        )
        raw_items = result.pop("items", None)
        base_name = os.path.splitext(file.filename or "seal")[0] or "seal"
        normalized_items: List[Dict[str, Any]] = []

        if raw_items and isinstance(raw_items, list):
            for item_index, raw_item in enumerate(raw_items):
                if not isinstance(raw_item, dict):
                    continue
                item_png = raw_item.get("result_png")
                if not item_png:
                    continue
                download_name = f"{base_name}_seal_{item_index + 1:02d}.png"
                item_url = _save_seal_output(item_png)
                item_payload = {
                    **{key: value for key, value in raw_item.items() if key != "result_png"},
                    "result_url": item_url,
                    "download_name": download_name,
                    "content_type": "image/png",
                }
                normalized_items.append(item_payload)
        else:
            result_png = result.pop("result_png")
            result_url = _save_seal_output(result_png)
            normalized_items.append(
                {
                    **result,
                    "candidate_index": 0,
                    "candidate_label": "印章 1",
                    "result_url": result_url,
                    "download_name": f"{base_name}_transparent.png",
                    "content_type": "image/png",
                }
            )

        if not normalized_items:
            return JSONResponse(status_code=400, content={"success": False, "error": "未生成可下载的印章结果。"})

        archive_url = ""
        archive_download_name = ""
        if len(normalized_items) > 1 and raw_items and isinstance(raw_items, list):
            archive_buffer = io.BytesIO()
            with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
                for item_index, raw_item in enumerate(raw_items):
                    if not isinstance(raw_item, dict) or not raw_item.get("result_png"):
                        continue
                    archive_file.writestr(f"{base_name}_seal_{item_index + 1:02d}.png", raw_item["result_png"])
            archive_url = _save_seal_archive(archive_buffer.getvalue())
            archive_download_name = f"{base_name}_seals.zip"

        selected_index = int(result.get("selected_index") or 0)
        if selected_index < 0 or selected_index >= len(normalized_items):
            selected_index = 0
        selected_item = normalized_items[selected_index]

        return {
            "success": True,
            "data": {
                **{key: value for key, value in result.items() if key not in {"result_png", "items"}},
                **selected_item,
                "source_url": source_url,
                "source_name": file.filename or "seal-source",
                "source_size_bytes": len(content),
                "source_content_type": file.content_type or "",
                "settings": settings,
                "selected_index": selected_index,
                "item_count": len(normalized_items),
                "items": normalized_items,
                "archive_url": archive_url,
                "archive_download_name": archive_download_name,
            },
        }
    except RuntimeError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": str(exc)})
    except Exception as exc:
        print(f"[SealExtract] API error: {exc}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/voice/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...)):
    """
    [File mode] upload file -> store -> async transcription (for long recordings)
    """
    if not submit_file_task: return {"error": "Voice Service Unavailable"}
    try:
        try:
            resolved_user_id = _resolve_request_user_id(request, allow_anonymous=True)
        except ValueError as exc:
            return JSONResponse(status_code=401, content={"error": str(exc)})
        task_id = await submit_file_task(file, user_id=resolved_user_id)
        task_info = get_task_result(task_id)
        file_path = task_info.get('file_path')

        if not task_id: return {"error": "File save failed"}
        return {
            "task_id": task_id,
            "message": "Task submitted via direct upload",
            "file_path": file_path,
            "result_link": f"/tasks?task={task_id}",
        }
    except Exception as e:
        print(f"[Voice] API error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# 新增：实时语音/短音频端点
@app.post("/api/voice/instant")
async def transcribe_instant(request: Request, file: UploadFile = File(...)):
    """
    [Realtime mode] upload bytes directly -> return text synchronously (for short recordings)
    """
    if not baidu_asr_from_bytes: return {"error": "Voice Manager Unavailable"}
    try:
        try:
            resolved_user_id = _resolve_request_user_id(request, allow_anonymous=True)
        except ValueError as exc:
            return JSONResponse(status_code=401, content={"error": str(exc)})
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
        task_record = (
            create_instant_task(
                original_name=file.filename or "instant.wav",
                file_path=stored_path,
                user_id=resolved_user_id,
                result_text=text,
                error_message=None if text and not str(text).startswith("❌") and not str(text).startswith("[ERROR]") else str(text or "转写失败"),
            )
            if create_instant_task
            else None
        )
        return {
            "success": True,
            "text": text,
            "file_path": stored_path,
            "task_id": task_record.get("task_id") if isinstance(task_record, dict) else None,
            "result_link": f"/tasks?task={task_record.get('task_id')}" if isinstance(task_record, dict) else None,
        }
    except Exception as e:
        print(f"[Voice] realtime API error: {e}")
        if create_instant_task:
            try:
                task_record = create_instant_task(
                    original_name=file.filename or "instant.wav",
                    file_path=None,
                    user_id=locals().get("resolved_user_id"),
                    result_text=None,
                    error_message=str(e),
                )
                return {
                    "error": str(e),
                    "task_id": task_record.get("task_id") if isinstance(task_record, dict) else None,
                    "result_link": f"/tasks?task={task_record.get('task_id')}" if isinstance(task_record, dict) else None,
                }
            except Exception:
                pass
        return {"error": str(e)}


@app.post("/api/voice/transcribe_supabase")
async def transcribe_via_supabase(request: Request, req: TranscribeRequest):
    if not submit_supabase_task: return {"error": "Voice Service Unavailable"}
    try:
        try:
            resolved_user_id = _resolve_request_user_id(request, allow_anonymous=True)
        except ValueError as exc:
            return JSONResponse(status_code=401, content={"error": str(exc)})
        task_id = await submit_supabase_task(req.file_path, req.original_name, user_id=resolved_user_id)
        return {"task_id": task_id, "message": "Task submitted via Supabase", "result_link": f"/tasks?task={task_id}"}
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

