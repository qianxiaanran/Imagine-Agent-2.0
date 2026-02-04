# -*- coding: utf-8 -*-
import os
import time
import threading
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 初始化变量
auth_router = None
user_router = None
chat_router = None
audit_router = None
admin_router = None
upload_document_to_vector_store = None
delete_user_documents = None
store_text_to_vector_store = None
submit_file_task = None
get_task_result = None
submit_supabase_task = None
get_file_signed_url = None
upload_bytes_to_supabase = None
OCRManager = None
ocr_agent = None
save_context = None
voice_ws_proxy = None
generate_report_outline = None
generate_email_draft = None
# âœ?OCR æ™ºèƒ½å½•å…¥
parse_ocr_content = None
save_ocr_record = None
# ✨ 新增
baidu_asr_from_bytes = None


def _save_ocr_upload(content: bytes, filename: str) -> str:
    base_dir = os.path.dirname(__file__)
    date_folder = datetime.utcnow().strftime("%Y%m%d")
    ext = os.path.splitext(filename or "")[1]
    if ext and len(ext) > 10:
        ext = ""
    safe_name = f"{uuid.uuid4().hex}{ext}"
    rel_dir = os.path.join("static", "ocr", date_folder)
    abs_dir = os.path.join(base_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, safe_name)
    with open(abs_path, "wb") as f:
        f.write(content)
    return f"/api/static/ocr/{date_folder}/{safe_name}"

try:
    from auth_router import router as auth_router, user_router
    from chat_router import router as chat_router
    from audit_router import router as audit_router
    from admin_router import router as admin_router
    from documents_processing import upload_document_to_vector_store, delete_user_documents, store_text_to_vector_store
    from voice_files_processing import submit_file_task, get_task_result, submit_supabase_task, get_file_signed_url, upload_bytes_to_supabase
    from ocr_manager import OCRManager
    from history_manager import save_context
    import share_manager
    from report_email_manager import generate_report_outline, generate_email_draft
    from ocr_structured import parse_ocr_content, save_ocr_record
    import voice_ws_proxy
    from admin_utils import _bearer_token, _get_token_iat, _get_user_from_token, _fetch_profile
    # ✨ 导入同步识别函数
    from voice_manager import baidu_asr_from_bytes
    from deepseek_llm import warmup_models

    print("✅ 模块加载成功")
except Exception as e:
    warmup_models = None
    print(f"❌ [ImportError] 无法导入模块（部分功能可能不可用）：{e}")
    import traceback
    traceback.print_exc()

# Share 模块独立加载
share_manager = None
try:
    import share_manager as _share_manager

    share_manager = _share_manager
    print("✅ [Share] share_manager 已启用")
except Exception as e:
    print(f"⚠️ [Share] share_manager 未启用: {e}")
    import traceback
    traceback.print_exc()

app = FastAPI(title="Enterprise AI API")

@app.on_event("startup")
def _warmup_models():
    if os.getenv("LLM_WARMUP", "true").lower() == "false":
        return
    if not warmup_models:
        return
    threading.Thread(target=warmup_models, daemon=True).start()


if OCRManager:
    try:
        ocr_agent = OCRManager()
        print("✅ OCR 引擎挂载成功")
    except Exception as e:
        print(f"❌ OCR 引擎初始化失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠️ OCR 模块未加载，跳过初始化")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if "health" not in request.url.path and "result" not in request.url.path:
        print(f"\n📨 [网络请求] {request.method} {request.url.path}")
    start = time.time()
    response = await call_next(request)
    if "health" not in request.url.path and "result" not in request.url.path:
        print(f"📤 完成 | 状态码 {response.status_code} | 耗时 {time.time() - start:.2f}s")
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
            profile = _fetch_profile(user.id) if "_fetch_profile" in globals() else None
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

os.makedirs("static/temp_audio", exist_ok=True)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_root")
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static_api")

if auth_router: app.include_router(auth_router)
if user_router: app.include_router(user_router)
if chat_router:
    app.include_router(chat_router)
else:
    print("❌ 警告: Chat Router 未加载，/api/chat 接口将不可用")
if audit_router:
    app.include_router(audit_router)
else:
    print("⚠️ Audit Router not loaded, /api/audit endpoints unavailable")
if admin_router:
    app.include_router(admin_router)
else:
    print("⚠️ Admin Router not loaded, /api/admin endpoints unavailable")
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
    return {"success": False, "error": "Failed to create share link"}


@app.get("/api/public/share/{token}")
async def get_share_content(token: str):
    if not share_manager: return {"success": False, "error": "Share feature is disabled on server"}
    result = share_manager.get_shared_content(token)
    if "error" in result: return {"success": False, "error": result["error"]}
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
    if not ocr_agent: return {"error": "OCR 服务未就绪"}
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
        if result.get("text") and not result["text"].startswith("❌"):
            ocr_agent.store(result["text"], file.filename)
        return {"success": True, "data": result}
    except Exception as e:
        print(f"❌ OCR 接口异常: {e}")
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
    【文件模式】上传文件 -> 存储 -> 异步转写 (适合长录音)
    """
    if not submit_file_task: return {"error": "Voice Service Unavailable"}
    try:
        task_id = await submit_file_task(file)
        task_info = get_task_result(task_id)
        file_path = task_info.get('file_path')

        if not task_id: return {"error": "文件保存失败"}
        return {
            "task_id": task_id,
            "message": "Task submitted via direct upload",
            "file_path": file_path
        }
    except Exception as e:
        print(f"❌ 接口异常: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# ✨ [新增] 实时语音/短语音识别接口
@app.post("/api/voice/instant")
async def transcribe_instant(file: UploadFile = File(...)):
    """
    【实时模式】直接上传字节流 -> 同步返回文本 (适合 VoiceRecorder 录制的短语音)
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
        # 调用 voice_manager 中的同步接口
        text = baidu_asr_from_bytes(content, file.filename)
        return {"success": True, "text": text, "file_path": stored_path}
    except Exception as e:
        print(f"❌ 实时语音接口异常: {e}")
        return {"error": str(e)}


@app.post("/api/voice/transcribe_supabase")
async def transcribe_via_supabase(req: TranscribeRequest):
    if not submit_supabase_task: return {"error": "Voice Service Unavailable"}
    try:
        task_id = await submit_supabase_task(req.file_path, req.original_name)
        return {"task_id": task_id, "message": "Task submitted via Supabase"}
    except Exception as e:
        print(f"❌ Supabase 接口异常: {e}")
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


# ✨ [修改] RAG 上传接口：返回 preview (预览内容)
@app.post("/api/documents/upload")
async def upload_docs(user_id: str = Form(...), files: List[UploadFile] = File(...)):
    try:
        if delete_user_documents: delete_user_documents(user_id)
    except:
        pass
    ok, fail = 0, []
    previews = []  # 收集成功文档的预览
    if not upload_document_to_vector_store: return {"error": "Document Service Unavailable"}
    for f in files:
        try:
            content = await f.read()
            # ✨ 接收 3 个返回值
            success, msg, preview_text = upload_document_to_vector_store(content, f.filename, user_id)
            if success:
                ok += 1
                if preview_text:
                    previews.append(f"--- 文档: {f.filename} ---\n{preview_text}")
            else:
                fail.append({"file": f.filename, "error": msg})
        except Exception as e:
            fail.append({"file": f.filename, "error": str(e)})

    return {
        "status": "success",
        "ok": ok,
        "failed": len(fail),
        "errors": fail,
        "previews": "\n\n".join(previews)  # 返回拼接后的预览
    }


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

    print("🚀 FastAPI 已启动，监听 18001")
    uvicorn.run(app, host="0.0.0.0", port=18001, ws_ping_interval=20, ws_ping_timeout=20)
