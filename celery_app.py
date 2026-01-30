"""
Celery configuration and task definitions for the processing pipeline.

Uses Redis as broker, result backend, and stage-level cache.
Converts the 9 pipeline stages into chained Celery tasks with progress reporting.
"""

import os

from celery import Celery

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1")

# Create Celery app
celery_app = Celery(
    "shiny_handouts", broker=REDIS_URL, backend=REDIS_URL, include=["tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Result backend settings
    result_expires=86400,  # 24 hours
    result_extended=True,
    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for long-running tasks
    worker_concurrency=4,
    # Task time limits
    task_soft_time_limit=3600,  # 1 hour soft limit
    task_time_limit=3700,  # 1 hour 1 minute 40 seconds hard limit
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


def get_celery_app() -> Celery:
    """Get the configured Celery app instance."""
    return celery_app
    return celery_app
