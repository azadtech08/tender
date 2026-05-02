"""Scrape job Celery task — real Playwright implementation.

DAG per job:
  1. Mark job running
  2. For each keyword (sequential, rate-limited):
       a. GemScraper.scrape_keyword() → list of tender dicts
       b. Upsert each tender into DB
       c. Publish job_events (keyword_start / card_scraped / pdf_parsed / keyword_done)
  3. Mark job completed (or failed)
"""

import time
from datetime import datetime, timezone

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import Job, JobEvent, Tender
from scraper.gem_scraper import GemScraper
from tasks.webhook_fire import fire_job_event

logger = structlog.get_logger(__name__)

# Sync SQLAlchemy engine (Celery tasks are synchronous)
_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)


def _publish_event(session: Session, job_id: int, event_type: str, payload: dict) -> None:
    event = JobEvent(job_id=job_id, event_type=event_type, payload=payload)
    session.add(event)
    session.commit()


def _upsert_tender(session: Session, job_id: int, tenant_id: str, data: dict) -> bool:
    """Insert tender, skipping duplicates (tender_ref_no + job_id).

    Returns True if a new row was inserted, False if skipped.
    """
    stmt = (
        pg_insert(Tender)
        .values(
            job_id=job_id,
            tenant_id=tenant_id,
            **data,
        )
        .on_conflict_do_nothing(
            index_elements=["tender_ref_no", "job_id"],
        )
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount > 0


@celery_app.task(
    bind=True,
    name="tasks.scrape_job.run_scrape_job",
    max_retries=2,
    soft_time_limit=1800,
    time_limit=3600,
)
def run_scrape_job(self, job_id: int) -> dict:
    """Execute a GeM scraping job.

    Reads keywords/config from the Job row, scrapes GeM portal via Playwright,
    persists Tender rows, and publishes job_events for SSE streaming.
    """
    log = logger.bind(job_id=job_id, task_id=self.request.id)
    log.info("scrape_job.started")

    with Session(_engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            log.error("scrape_job.job_not_found")
            return {"error": "job not found"}

        keywords: list[str] = job.keywords if isinstance(job.keywords, list) else []
        cards_per_kw: int = job.cards_per_kw or 3
        min_value: float | None = float(job.min_value) if job.min_value else None
        tenant_id: str = job.tenant_id

        try:
            # Mark running
            job.status = "running"
            job.started_at = datetime.now(tz=timezone.utc)
            job.total_keywords = len(keywords)
            job.done_keywords = 0
            job.total_tenders = 0
            session.commit()
            _publish_event(session, job_id, "status_change", {"status": "running"})

            scraper = GemScraper(
                headless=settings.headless,
                download_dir=settings.download_dir,
            )

            total_tenders = 0

            for keyword in keywords:
                log.info("scrape_job.keyword_start", keyword=keyword)
                _publish_event(session, job_id, "keyword_start", {"keyword": keyword})

                def on_event(event_type: str, payload: dict, _job_id: int = job_id) -> None:
                    with Session(_engine) as evt_session:
                        _publish_event(evt_session, _job_id, event_type, payload)

                tenders = scraper.scrape_keyword(
                    keyword=keyword,
                    cards_per_kw=cards_per_kw,
                    min_value=min_value,
                    on_event=on_event,
                )

                inserted = 0
                for tender_data in tenders:
                    try:
                        ok = _upsert_tender(session, job_id, tenant_id, tender_data)
                        if ok:
                            inserted += 1
                    except Exception as exc:
                        log.warning("scrape_job.tender_insert_failed", error=str(exc))

                total_tenders += inserted
                job.done_keywords = (job.done_keywords or 0) + 1
                job.total_tenders = total_tenders
                session.commit()

                _publish_event(
                    session,
                    job_id,
                    "keyword_done",
                    {"keyword": keyword, "tenders_found": inserted},
                )
                log.info("scrape_job.keyword_done", keyword=keyword, tenders_found=inserted)

                # Inter-keyword pause (anti-bot)
                if keyword != keywords[-1]:
                    time.sleep(2)

            # Publish "complete" event BEFORE committing "completed" status so the
            # SSE stream delivers it to the client before the server-side loop closes.
            _publish_event(session, job_id, "complete", {"total_tenders": total_tenders})

            # Mark completed
            job.status = "completed"
            job.completed_at = datetime.now(tz=timezone.utc)
            session.commit()
            log.info("scrape_job.completed", total_tenders=total_tenders)

            # Fire outbound webhooks (best-effort, async)
            fire_job_event.delay(
                tenant_id=tenant_id,
                event="job.completed",
                payload={"job_id": job_id, "total_tenders": total_tenders},
            )

            return {"status": "completed", "job_id": job_id, "total_tenders": total_tenders}

        except Exception as exc:
            log.exception("scrape_job.failed", error=str(exc))
            try:
                job.status = "failed"
                job.error_message = str(exc)
                job.completed_at = datetime.now(tz=timezone.utc)
                session.commit()
                _publish_event(session, job_id, "error", {"message": str(exc)})
                # Fire outbound webhooks (best-effort, async)
                fire_job_event.delay(
                    tenant_id=tenant_id,
                    event="job.failed",
                    payload={"job_id": job_id, "error": str(exc)},
                )
            except Exception:
                pass
            raise self.retry(exc=exc, countdown=30)
