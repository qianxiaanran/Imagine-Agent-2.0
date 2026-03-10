from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from documents_processing import delete_user_documents, upload_document_to_vector_store
from runtime_storage import RUNTIME_CACHE_ROOT, ensure_runtime_layout


DOCUMENT_TASK_ROOT = Path(RUNTIME_CACHE_ROOT) / "document_upload_tasks"
DOCUMENT_TASK_STATE_DIR = DOCUMENT_TASK_ROOT / "state"
DOCUMENT_TASK_INPUT_DIR = DOCUMENT_TASK_ROOT / "inputs"
DOCUMENT_UPLOAD_TASKS: Dict[str, Dict[str, Any]] = {}
DOCUMENT_UPLOAD_TASK_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_task_layout() -> None:
    ensure_runtime_layout()
    DOCUMENT_TASK_STATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_TASK_INPUT_DIR.mkdir(parents=True, exist_ok=True)


def _task_state_path(task_id: str) -> Path:
    _ensure_task_layout()
    return DOCUMENT_TASK_STATE_DIR / f"{task_id}.json"


def _task_input_dir(task_id: str) -> Path:
    _ensure_task_layout()
    return DOCUMENT_TASK_INPUT_DIR / task_id


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _save_task(task_id: str, payload: Dict[str, Any]) -> None:
    with DOCUMENT_UPLOAD_TASK_LOCK:
        DOCUMENT_UPLOAD_TASKS[task_id] = dict(payload)
    try:
        _write_json(_task_state_path(task_id), payload)
    except Exception as e:
        print(f"[Doc Upload] Persist task failed ({task_id}): {e}")


def _load_task(task_id: str) -> Optional[Dict[str, Any]]:
    with DOCUMENT_UPLOAD_TASK_LOCK:
        existing = DOCUMENT_UPLOAD_TASKS.get(task_id)
        if existing:
            return dict(existing)
    path = _task_state_path(task_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            with DOCUMENT_UPLOAD_TASK_LOCK:
                DOCUMENT_UPLOAD_TASKS[task_id] = dict(payload)
            return payload
    except Exception:
        return None
    return None


def _patch_task(task_id: str, **updates: Any) -> Dict[str, Any]:
    task = _load_task(task_id) or {"task_id": task_id}
    task.update(updates)
    task["updated_at"] = _now_iso()
    _save_task(task_id, task)
    return task


def _cleanup_task_inputs(task_id: str) -> None:
    try:
        shutil.rmtree(_task_input_dir(task_id), ignore_errors=True)
    except Exception:
        pass


def _normalize_upload_result(ok: int, errors: List[Dict[str, Any]]) -> tuple[str, str]:
    if ok > 0 and not errors:
        return "completed", "success"
    if ok > 0:
        return "completed", "partial"
    return "failed", "failed"


def process_document_upload_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        raise RuntimeError(f"Document upload task not found: {task_id}")

    files = task.get("files") or []
    user_id = str(task.get("user_id") or "anonymous").strip() or "anonymous"
    replace_existing = bool(task.get("replace_existing"))
    total_files = len(files)
    if total_files <= 0:
        _patch_task(
            task_id,
            status="failed",
            result_status="failed",
            progress=100,
            error_message="No files to process",
            completed_at=_now_iso(),
        )
        return _load_task(task_id) or {"task_id": task_id, "status": "failed"}

    _patch_task(
        task_id,
        status="processing",
        result_status="processing",
        progress=0,
        started_at=_now_iso(),
        processed_count=0,
        ok=0,
        failed=0,
        errors=[],
        previews="",
        current_file=None,
        error_message=None,
    )

    if replace_existing and delete_user_documents:
        try:
            delete_user_documents(user_id)
        except Exception as e:
            print(f"[Doc Upload] delete existing documents failed for {user_id}: {e}")

    ok_count = 0
    errors: List[Dict[str, Any]] = []
    previews: List[str] = []

    try:
        for index, item in enumerate(files):
            filename = str(item.get("filename") or f"document-{index + 1}").strip() or f"document-{index + 1}"
            file_path = str(item.get("file_path") or "").strip()
            _patch_task(
                task_id,
                current_file=filename,
                processed_count=index,
                progress=min(95, int((index / max(total_files, 1)) * 100)),
            )

            if not file_path or not Path(file_path).exists():
                errors.append({"file": filename, "error": f"Task input file not found: {file_path}"})
                _patch_task(task_id, failed=len(errors), errors=errors)
                continue

            try:
                file_bytes = Path(file_path).read_bytes()
                success, message, preview_text = upload_document_to_vector_store(file_bytes, filename, user_id)
                if success:
                    ok_count += 1
                    if preview_text:
                        previews.append(f"--- Document: {filename} ---\n{preview_text}")
                else:
                    errors.append({"file": filename, "error": message})
            except Exception as e:
                errors.append({"file": filename, "error": str(e)})

            _patch_task(
                task_id,
                ok=ok_count,
                failed=len(errors),
                errors=errors,
                previews="\n\n".join(previews),
                processed_count=index + 1,
                progress=min(95, int(((index + 1) / max(total_files, 1)) * 100)),
            )

        final_status, result_status = _normalize_upload_result(ok_count, errors)
        return _patch_task(
            task_id,
            status=final_status,
            result_status=result_status,
            ok=ok_count,
            failed=len(errors),
            errors=errors,
            previews="\n\n".join(previews),
            progress=100,
            processed_count=total_files,
            current_file=None,
            completed_at=_now_iso(),
            error_message="" if ok_count > 0 else "; ".join(
                str(item.get("error") or item.get("file") or "").strip() for item in errors
            ),
        )
    except Exception as e:
        _patch_task(
            task_id,
            status="failed",
            result_status="failed",
            progress=100,
            current_file=None,
            completed_at=_now_iso(),
            error_message=str(e),
        )
        raise
    finally:
        _cleanup_task_inputs(task_id)


def _run_document_upload_task_inline(task_id: str) -> None:
    def _target() -> None:
        try:
            process_document_upload_task(task_id)
        except Exception as e:
            print(f"[Doc Upload] task {task_id} failed: {e}")

    thread = threading.Thread(
        target=_target,
        name=f"doc-upload-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


def submit_document_upload_task(
    *,
    user_id: str,
    files: List[Dict[str, Any]],
    replace_existing: bool = False,
) -> Dict[str, Any]:
    _ensure_task_layout()
    task_id = str(uuid.uuid4())
    input_dir = _task_input_dir(task_id)
    input_dir.mkdir(parents=True, exist_ok=True)

    stored_files: List[Dict[str, Any]] = []
    for index, item in enumerate(files or []):
        filename = str(item.get("filename") or f"document-{index + 1}").strip() or f"document-{index + 1}"
        safe_name = filename.replace("\\", "_").replace("/", "_")
        file_path = input_dir / safe_name
        file_path.write_bytes(bytes(item.get("content") or b""))
        stored_files.append({
            "filename": filename,
            "file_path": str(file_path),
            "content_type": str(item.get("content_type") or ""),
            "size": int(item.get("size") or 0),
        })

    task = {
        "task_id": task_id,
        "status": "queued",
        "result_status": "queued",
        "progress": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "user_id": str(user_id or "anonymous").strip() or "anonymous",
        "replace_existing": bool(replace_existing),
        "file_count": len(stored_files),
        "files": stored_files,
        "processed_count": 0,
        "ok": 0,
        "failed": 0,
        "errors": [],
        "previews": "",
        "current_file": None,
        "error_message": None,
    }
    _save_task(task_id, task)
    _run_document_upload_task_inline(task_id)
    return task


def get_document_upload_task(task_id: str) -> Dict[str, Any]:
    task = _load_task(task_id)
    if not task:
        return {"task_id": task_id, "status": "not_found", "result_status": "not_found"}
    return task
