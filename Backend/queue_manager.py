from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional, Tuple

_QUEUE_IMPORT_ERROR: Optional[Exception] = None
try:
    from redis import Redis  # type: ignore
    from rq import Queue, Retry  # type: ignore
    from rq.job import Job  # type: ignore
except Exception as e:  # pragma: no cover - import fallback
    Redis = None  # type: ignore
    Queue = None  # type: ignore
    Retry = None  # type: ignore
    Job = None  # type: ignore
    _QUEUE_IMPORT_ERROR = e


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
QUEUE_DEFAULT_TIMEOUT = int(os.getenv("QUEUE_DEFAULT_TIMEOUT", "1800"))

VOICE_QUEUE_NAME = os.getenv("VOICE_QUEUE_NAME", "voice_tasks")
AUDIT_QUEUE_NAME = os.getenv("AUDIT_QUEUE_NAME", "audit_tasks")


_redis_conn: Optional[Any] = None
_queue_cache: Dict[Tuple[str, int], Any] = {}


def _ensure_queue_libs() -> None:
    if Redis is None or Queue is None or Retry is None:
        raise RuntimeError(
            f"Redis/RQ dependencies are missing. Install requirements first. root cause: {_QUEUE_IMPORT_ERROR}"
        )


def get_redis_connection() -> Any:
    _ensure_queue_libs()
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = Redis.from_url(REDIS_URL)
    return _redis_conn


def ensure_redis() -> Any:
    conn = get_redis_connection()
    conn.ping()
    return conn


def get_queue(name: str, *, default_timeout: Optional[int] = None) -> Any:
    _ensure_queue_libs()
    timeout = int(default_timeout or QUEUE_DEFAULT_TIMEOUT)
    cache_key = (name, timeout)
    queue = _queue_cache.get(cache_key)
    if queue is None:
        queue = Queue(name=name, connection=get_redis_connection(), default_timeout=timeout)
        _queue_cache[cache_key] = queue
    return queue


def enqueue_job(
    *,
    queue_name: str,
    func: Callable[..., Any],
    kwargs: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    retry_max: int = 0,
    timeout: Optional[int] = None,
    result_ttl: int = 24 * 3600,
    failure_ttl: int = 7 * 24 * 3600,
) -> Job:
    _ensure_queue_libs()
    queue = get_queue(queue_name, default_timeout=timeout)
    retry = Retry(max=retry_max) if retry_max and retry_max > 0 else None
    enqueue_kwargs: Dict[str, Any] = {
        "kwargs": kwargs or {},
        "job_id": job_id,
        "retry": retry,
        "result_ttl": result_ttl,
        "failure_ttl": failure_ttl,
    }
    if timeout is not None:
        # RQ 1.x accepts `job_timeout`; older wrappers may rely on queue default_timeout.
        enqueue_kwargs["job_timeout"] = int(timeout)
    # NOTE: RQ 1.16 Queue.enqueue requires the function as the first positional arg (`f`).
    return queue.enqueue(func, **enqueue_kwargs)


def fetch_job(job_id: str) -> Optional[Any]:
    if not job_id:
        return None
    _ensure_queue_libs()
    try:
        return Job.fetch(job_id, connection=get_redis_connection())
    except Exception:
        return None
