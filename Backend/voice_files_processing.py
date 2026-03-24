import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from supabase_client import require_supabase, supabase
from task_registry import build_task_result_link, get_task, upsert_task
from voice_manager import transcribe_audio_via_chunks


STORAGE_BUCKET = "voice_uploads"
VOICE_TASK_PREFIX = "voice:task:"

# 语音任务只使用进程内状态，不再依赖 Redis/RQ。
TRANSCRIPTION_TASKS: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_key(task_id: str) -> str:
    return f"{VOICE_TASK_PREFIX}{task_id}"


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    return TRANSCRIPTION_TASKS.get(task_id)


def _save_task(task_id: str, payload: Dict[str, Any]) -> None:
    TRANSCRIPTION_TASKS[task_id] = payload


def _sync_task_registry(task: Dict[str, Any]) -> None:
    if not isinstance(task, dict):
        return
    task_id = str(task.get("task_id") or "").strip()
    if not task_id:
        return
    status = str(task.get("status") or "queued")
    progress_map = {
        "queued": 0,
        "processing": 58,
        "completed": 100,
        "failed": 100,
    }
    upsert_task(
        {
            "task_id": task_id,
            "task_type": "voice",
            "user_id": str(task.get("user_id") or "anonymous").strip() or "anonymous",
            "title": f"语音转写 · {task.get('filename') or '录音文件'}",
            "status": status,
            "progress": progress_map.get(status, task.get("progress", 0)),
            "started_at": task.get("started_at") or task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "error_message": task.get("error_message"),
            "result_link": build_task_result_link(task_id),
            "retry_supported": True,
            "detail": {
                "filename": task.get("filename"),
                "file_path": task.get("file_path"),
                "result_text": task.get("result") if status == "completed" else None,
                "started_at": task.get("started_at"),
                "completed_at": task.get("completed_at"),
            },
            "source_payload": {
                "filename": task.get("filename"),
                "file_path": task.get("file_path"),
                "user_id": str(task.get("user_id") or "anonymous").strip() or "anonymous",
            },
        }
    )


def _patch_task(task_id: str, **updates: Any) -> Dict[str, Any]:
    task = _load_task(task_id) or {"task_id": task_id}
    task.update(updates)
    task["updated_at"] = _now_iso()
    _save_task(task_id, task)
    _sync_task_registry(task)
    return task


def _normalize_signed_url(signed_url_resp: Any) -> str:
    if isinstance(signed_url_resp, dict):
        return (
            signed_url_resp.get("signedURL")
            or signed_url_resp.get("signed_url")
            or signed_url_resp.get("signedUrl")
            or ""
        )
    if isinstance(signed_url_resp, str):
        return signed_url_resp
    return str(signed_url_resp)


def _download_audio_bytes(remote_file_path: str) -> bytes:
    blob = require_supabase().storage.from_(STORAGE_BUCKET).download(remote_file_path)
    if hasattr(blob, "data"):
        blob = getattr(blob, "data")
    if isinstance(blob, str):
        blob = blob.encode("utf-8", errors="ignore")
    if not isinstance(blob, (bytes, bytearray)):
        raise RuntimeError("Storage download returned invalid payload")
    return bytes(blob)


def _transcribe_bytes(audio_bytes: bytes, original_filename: str) -> str:
    result_text = transcribe_audio_via_chunks(audio_bytes, filename=original_filename)
    if not result_text:
        raise RuntimeError("ASR returned empty result")
    if str(result_text).strip().startswith("❌"):
        raise RuntimeError(str(result_text))
    return result_text


def _create_task_payload(task_id: str, original_name: str, file_path: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "queue_job_id": None,
        "status": "queued",
        "created_at": _now_iso(),
        "filename": original_name,
        "file_path": file_path,
        "user_id": str(user_id or "anonymous").strip() or "anonymous",
        "result": None,
        "error_message": None,
    }


def create_instant_task(
    *,
    original_name: str,
    file_path: Optional[str],
    user_id: Optional[str],
    result_text: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    payload = _create_task_payload(task_id, original_name, file_path, user_id)
    _save_task(task_id, payload)
    _sync_task_registry(payload)

    started_at = _now_iso()
    status = "failed" if error_message else "completed"
    _patch_task(
        task_id,
        status=status,
        started_at=started_at,
        completed_at=_now_iso(),
        result=result_text if not error_message else (result_text or f"处理异常: {error_message}"),
        error_message=error_message,
    )
    return _load_task(task_id) or {"task_id": task_id, "status": status}


def process_transcription_task(task_id: str, remote_file_path: str, original_filename: str) -> Dict[str, Any]:
    _patch_task(task_id, status="processing", started_at=_now_iso())
    try:
        print(f"[Voice ASR] Use local chunked transcription from storage bytes: {remote_file_path}")
        audio_bytes = _download_audio_bytes(remote_file_path)
        result_text = _transcribe_bytes(audio_bytes, original_filename)
        _patch_task(
            task_id,
            status="completed",
            result=result_text,
            completed_at=_now_iso(),
            error_message=None,
        )
        return {"task_id": task_id, "status": "completed"}
    except Exception as e:
        err = str(e)
        _patch_task(
            task_id,
            status="failed",
            result=f"处理异常: {err}",
            error_message=err,
            completed_at=_now_iso(),
        )
        raise


def _run_voice_storage_task_async(task_id: str, remote_file_path: str, original_filename: str) -> None:
    def _target() -> None:
        try:
            process_transcription_task(task_id, remote_file_path, original_filename)
        except Exception as e:
            print(f"[Voice Task] storage task {task_id} failed: {e}")

    thread = threading.Thread(
        target=_target,
        name=f"voice-storage-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


def _run_voice_bytes_task_async(task_id: str, audio_bytes: bytes, original_filename: str) -> None:
    def _target() -> None:
        _patch_task(task_id, status="processing", started_at=_now_iso())
        try:
            print(f"[Voice ASR] Use local chunked transcription directly from uploaded bytes: {original_filename}")
            result_text = _transcribe_bytes(audio_bytes, original_filename)
            _patch_task(
                task_id,
                status="completed",
                result=result_text,
                completed_at=_now_iso(),
                error_message=None,
            )
        except Exception as e:
            err = str(e)
            _patch_task(
                task_id,
                status="failed",
                result=f"处理异常: {err}",
                error_message=err,
                completed_at=_now_iso(),
            )
            print(f"[Voice Task] bytes task {task_id} failed: {e}")

    thread = threading.Thread(
        target=_target,
        name=f"voice-bytes-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


async def submit_supabase_task(file_path: str, original_name: str, user_id: Optional[str] = None) -> str:
    task_id = str(uuid.uuid4())
    payload = _create_task_payload(task_id, original_name, file_path, user_id)
    _save_task(task_id, payload)
    _sync_task_registry(payload)
    _run_voice_storage_task_async(task_id, file_path, original_name)
    return task_id


def get_task_result(task_id: str):
    task = _load_task(task_id)
    if task:
        return task
    return {"status": "not_found"}


async def upload_bytes_to_supabase(file_bytes: bytes, filename: str, content_type: str) -> Optional[str]:
    try:
        unique_name = f"{uuid.uuid4()}_{filename}"
        path = f"uploads/{unique_name}"
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
        return path
    except Exception as e:
        print(f"Upload to Supabase failed: {e}")
        return None


def get_file_signed_url(file_path: str, expire=3600):
    try:
        if not file_path:
            return None
        res = supabase.storage.from_(STORAGE_BUCKET).create_signed_url(file_path, expire)
        return _normalize_signed_url(res)
    except Exception as e:
        print(f"Get Signed URL failed: {e}")
        return None


async def submit_file_task(file, user_id: Optional[str] = None) -> str:
    content = await file.read()
    stored_path = await upload_bytes_to_supabase(content, file.filename, file.content_type)

    task_id = str(uuid.uuid4())
    payload = _create_task_payload(task_id, file.filename, stored_path, user_id)
    _save_task(task_id, payload)
    _sync_task_registry(payload)
    _run_voice_bytes_task_async(task_id, content, file.filename)
    return task_id


async def retry_voice_task(task_id: str) -> Dict[str, Any]:
    current = _load_task(task_id) or get_task(task_id)
    if not isinstance(current, dict):
        raise RuntimeError("Task not found")
    file_path = str(current.get("file_path") or "").strip()
    filename = str(current.get("filename") or "recording.wav").strip() or "recording.wav"
    user_id = str(current.get("user_id") or "anonymous").strip() or "anonymous"
    if not file_path:
        raise RuntimeError("Missing source audio path")
    new_task_id = await submit_supabase_task(file_path, filename, user_id=user_id)
    return get_task(new_task_id) or get_task_result(new_task_id)
