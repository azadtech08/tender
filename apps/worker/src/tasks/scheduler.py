"""Celery Beat periodic task — fires due schedules.

Runs every minute. Queries schedules where:
  - is_active = true
  - next_run_at <= now (IST)

For each due schedule, dispatches run_scrape_job and advances next_run_at by 24 h.
"""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import Schedule
from sqlalchemy import create_engine

logger = structlog.get_logger(__name__)

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)


@celery_app.task(name="tasks.scheduler.tick")
def tick() -> dict:
    """Poll for due schedules and dispatch scrape jobs."""
    now = datetime.now(tz=timezone.utc)
    dispatched: list[int] = []

    with Session(_engine) as session:
        due = session.execute(
            select(Schedule).where(
                Schedule.is_active == True,  # noqa: E712
                Schedule.next_run_at <= now,
            )
        ).scalars().all()

        for schedule in due:
            try:
                celery_app.send_task(
                    "tasks.scrape_job.run_scrape_job",
                    args=[schedule.job_id],
                )
                schedule.last_run_at = now
                schedule.next_run_at = now + timedelta(days=1)
                dispatched.append(schedule.job_id)
                logger.info(
                    "scheduler.dispatched",
                    job_id=schedule.job_id,
                    next_run=schedule.next_run_at.isoformat(),
                )
            except Exception as exc:
                logger.error("scheduler.dispatch_failed", job_id=schedule.job_id, error=str(exc))

        if dispatched:
            session.commit()

    return {"dispatched_job_ids": dispatched, "checked_at": now.isoformat()}
