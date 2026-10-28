"""
Celery Application Configuration (Milestone 3)

Configures Celery with Redis broker and result backend.
Supports local Redis on loopback (redis://127.0.0.1:6379/0)
and eager mode (CELERY_TASK_ALWAYS_EAGER=true) for development/testing without Redis.
"""

from __future__ import annotations

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"))
ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"

celery_app = Celery(
    "business_reporting_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "300")),  # 5 min hard limit
    task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "240")),  # 4 min soft limit
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "2")),
    worker_prefetch_multiplier=1,
    task_always_eager=ALWAYS_EAGER,
    task_eager_propagates=True,
)
