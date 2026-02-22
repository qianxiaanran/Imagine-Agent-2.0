from __future__ import annotations

import os

from rq import Worker

from queue_manager import AUDIT_QUEUE_NAME, VOICE_QUEUE_NAME, ensure_redis, get_queue


def main() -> None:
    conn = ensure_redis()
    raw_names = os.getenv("RQ_QUEUES", f"{VOICE_QUEUE_NAME},{AUDIT_QUEUE_NAME}")
    queue_names = [name.strip() for name in raw_names.split(",") if name.strip()]
    queues = [get_queue(name) for name in queue_names]
    with_scheduler = os.getenv("RQ_WITH_SCHEDULER", "false").lower() in {"1", "true", "yes", "on"}

    audit_warmup_enabled = os.getenv("AUDIT_OCR_WARMUP", "true").lower() in {"1", "true", "yes", "on"}
    if audit_warmup_enabled and AUDIT_QUEUE_NAME in queue_names:
        try:
            from ocr_manager import get_shared_ocr_manager

            get_shared_ocr_manager()
            print("[RQ Worker] Audit OCR warmup completed")
        except Exception as e:
            print(f"[RQ Worker] Audit OCR warmup skipped: {e}")

    worker = Worker(queues=queues, connection=conn)
    worker.work(with_scheduler=with_scheduler)


if __name__ == "__main__":
    main()
