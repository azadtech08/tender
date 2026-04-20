"""Celery application for the GeM worker."""

from celery import Celery
from celery.schedules import crontab

from config import settings

celery_app = Celery(
    "gem-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    timezone="Asia/Kolkata",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["tasks"])

# Celery Beat schedules
celery_app.conf.beat_schedule = {
    # Poll for due scheduled scrape jobs every 60 seconds
    "scheduler-tick": {
        "task":     "tasks.scheduler.tick",
        "schedule": 60.0,
    },
    # Daily alert digest at 08:00 IST = 02:30 UTC
    "digest-daily": {
        "task":     "tasks.digest.send_daily_digests",
        "schedule": crontab(hour=2, minute=30),
    },
}
celery_app.conf.beat_scheduler = "celery.beat:PersistentScheduler"
