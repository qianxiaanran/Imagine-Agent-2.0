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

    worker = Worker(queues=queues, connection=conn)
    worker.work(with_scheduler=with_scheduler)


if __name__ == "__main__":
    main()
