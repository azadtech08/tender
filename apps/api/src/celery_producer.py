"""Minimal Celery producer for the API.

Creates a Celery app connected to Redis only for *sending* tasks.
The actual task implementations live in apps/worker.
"""

from celery import Celery

from config import settings

celery_app = Celery(broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
