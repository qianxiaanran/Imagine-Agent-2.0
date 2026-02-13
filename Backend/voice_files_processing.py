import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from queue_manager import VOICE_QUEUE_NAME, enqueue_job, fetch_job, get_redis_connection
from supabase_client import require_supabase, supabase
from voice_manager import get_format_from_filename, transcribe_audio_via_url


STORAGE_BUCKET = "voice_uploads"
VOICE_TASK_PREFIX = "voice:task:"
VOICE_TASK_TTL_SECONDS = int(os.getenv("VOICE_TASK_TTL_SECONDS", str(7 * 24 * 3600)))
VOICE_JOB_TIMEOUT_SECONDS = int(os.getenv("VOICE_JOB_TIMEOUT_SECONDS", "3600"))
VOICE_JOB_RETRY_MAX = int(os.getenv("VOICE_JOB_RETRY_MAX", "2"))
VOICE_INLINE_FALLBACK = os.getenv("VOICE_INLINE_FALLBACK", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# Fallback cache when Redis is temporarily unavailable.
TRANSCRIPTION_TASKS: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_key(task_id: str) -> str:
    return f"{VOICE_TASK_PREFIX}{task_id}"


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    try:
        raw = get_redis_connection().get(_task_key(task_id))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return TRANSCRIPTION_TASKS.get(task_id)


def _save_task(task_id: str, payload: Dict[str, Any]) -> None:
    TRANSCRIPTION_TASKS[task_id] = payload
    try:
        get_redis_connection().set(
            _task_key(task_id),
            json.dumps(payload, ensure_ascii=False),
            ex=VOICE_TASK_TTL_SECONDS,
        )
    except Exception as e:
        print(f"[Voice Queue] Redis write failed: {e}")


def _patch_task(task_id: str, **updates: Any) -> Dict[str, Any]:
    task = _load_task(task_id) or {"task_id": task_id}
    task.update(updates)
    task["updated_at"] = _now_iso()
    _save_task(task_id, task)
    return task


def _normalize_signed_url(signed_url_resp: Any) -> str:
    if isinstance(signed_url_resp, dict) and "signedURL" in signed_url_resp:
        return signed_url_resp["signedURL"]
    if isinstance(signed_url_resp, str):
        return signed_url_resp
    return str(signed_url_resp)


def process_transcription_task(task_id: str, remote_file_path: str, original_filename: str) -> Dict[str, Any]:
    _patch_task(task_id, status="processing", started_at=_now_iso())
    try:
        supabase_client = require_supabase()
        signed_url_resp = supabase_client.storage.from_(STORAGE_BUCKET).create_signed_url(remote_file_path, 3600 * 3)
        audio_url = _normalize_signed_url(signed_url_resp)

        file_fmt = get_format_from_filename(original_filename)
        result_text = transcribe_audio_via_url(audio_url, format=file_fmt)
        if not result_text:
            raise RuntimeError("ASR returned empty result")
        if str(result_text).strip().startswith("❌"):
            raise RuntimeError(str(result_text))

        _patch_task(task_id, status="completed", result=result_text, completed_at=_now_iso(), error_message=None)
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


def _run_voice_task_inline_async(task_id: str, remote_file_path: str, original_filename: str) -> None:
    """Fallback path when Redis/RQ is unavailable."""

    def _target() -> None:
        try:
            process_transcription_task(task_id, remote_file_path, original_filename)
        except Exception as e:
            print(f"[Voice Queue Fallback] task {task_id} failed: {e}")

    thread = threading.Thread(
        target=_target,
        name=f"voice-inline-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


async def submit_supabase_task(file_path: str, original_name: str) -> str:
    task_id = str(uuid.uuid4())
    queue_job_id = f"voice:{task_id}"

    _save_task(
        task_id,
        {
            "task_id": task_id,
            "queue_job_id": queue_job_id,
            "status": "queued",
            "created_at": _now_iso(),
            "filename": original_name,
            "file_path": file_path,
            "result": None,
            "error_message": None,
        },
    )

    try:
        enqueue_job(
            queue_name=VOICE_QUEUE_NAME,
            func=process_transcription_task,
            kwargs={
                "task_id": task_id,
                "remote_file_path": file_path,
                "original_filename": original_name,
            },
            job_id=queue_job_id,
            retry_max=VOICE_JOB_RETRY_MAX,
            timeout=VOICE_JOB_TIMEOUT_SECONDS,
        )
    except Exception as e:
        if VOICE_INLINE_FALLBACK:
            print(f"[Voice Queue] enqueue failed ({e}), fallback to inline worker thread")
            _patch_task(task_id, dispatch_mode="inline")
            _run_voice_task_inline_async(task_id, file_path, original_name)
            return task_id
        err = f"Queue enqueue failed: {e}"
        _patch_task(task_id, status="failed", error_message=err, result=err, completed_at=_now_iso())
        raise RuntimeError(err) from e

    return task_id


def _map_rq_status(status: str) -> str:
    s = (status or "").lower()
    if s in {"queued", "deferred", "scheduled"}:
        return "queued"
    if s in {"started"}:
        return "processing"
    if s in {"finished"}:
        return "completed"
    if s in {"failed", "stopped", "canceled"}:
        return "failed"
    return s or "unknown"


def get_task_result(task_id: str):
    task = _load_task(task_id)
    if task:
        job_id = task.get("queue_job_id")
        if job_id and task.get("status") in {"queued", "processing"}:
            try:
                job = fetch_job(job_id)
            except Exception:
                job = None
            if job:
                mapped = _map_rq_status(job.get_status(refresh=True))
                if mapped != task.get("status"):
                    task = _patch_task(task_id, status=mapped)
        return task

    try:
        job = fetch_job(f"voice:{task_id}")
    except Exception:
        job = None
    if job:
        status = _map_rq_status(job.get_status(refresh=True))
        return {
            "task_id": task_id,
            "queue_job_id": f"voice:{task_id}",
            "status": status,
            "created_at": None,
            "result": None,
        }

    return {"status": "not_found"}


async def upload_bytes_to_supabase(file_bytes: bytes, filename: str, content_type: str) -> str:
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
        if isinstance(res, dict) and "signedURL" in res:
            return res["signedURL"]
        if isinstance(res, str):
            return res
        return str(res)
    except Exception as e:
        print(f"Get Signed URL failed: {e}")
        return None


async def submit_file_task(file) -> str:
    content = await file.read()
    path = await upload_bytes_to_supabase(content, file.filename, file.content_type)

    if not path:
        raise Exception("Failed to upload file to storage")

    return await submit_supabase_task(path, file.filename)
