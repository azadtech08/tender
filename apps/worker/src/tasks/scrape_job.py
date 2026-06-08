"""Scrape job Celery task — Direct API for correct bid order + PDF for full field data.

DAG per job:
  1. Mark job running
  2. For each keyword:
       a. Fetch bids from GeM's internal JSON API (gem_proxy_scraper) — correct order
       b. For each bid: download PDF → parse → extract 23 fields
       c. Upsert tender into DB
       d. Publish job_events for SSE streaming
  3. Mark job completed (or failed)
"""

import os
import random
import time
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import Job, JobEvent, Tender
from scraper.gem_proxy_scraper import scrape_gem_direct
from scraper.gem_scraper import _download_pdf, _parse_amount, _safe_filename
from scraper.pdf_extractor import extract_fields, is_it_relevant, parse_pdf
from tasks.webhook_fire import fire_job_event
from utils.s3 import upload_file_from_path

logger = structlog.get_logger(__name__)

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)


def _str_to_date(s: str) -> date | None:
    """Parse DD/MM/YYYY string (from gem_proxy) to a date object."""
    if not s or s == "N/A":
        return None
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _str_to_datetime(s: str) -> datetime | None:
    """Parse DD/MM/YYYY string (from gem_proxy) to a UTC datetime."""
    if not s or s == "N/A":
        return None
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _publish_event(session: Session, job_id: int, event_type: str, payload: dict) -> None:
    event = JobEvent(job_id=job_id, event_type=event_type, payload=payload)
    session.add(event)
    session.commit()


def _upsert_tender(session: Session, job_id: int, tenant_id: str, data: dict) -> bool:
    """Upsert tender. Returns True if newly inserted."""
    insert_stmt = pg_insert(Tender).values(
        job_id=job_id,
        tenant_id=tenant_id,
        **data,
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["tender_ref_no", "job_id"],
        set_={
            "gem_position": insert_stmt.excluded.gem_position,
            "title":        insert_stmt.excluded.title,
            "ministry":     insert_stmt.excluded.ministry,
            "state":        insert_stmt.excluded.state,
            "tender_value": insert_stmt.excluded.tender_value,
            "bid_end_date": insert_stmt.excluded.bid_end_date,
            "pdf_s3_key":   insert_stmt.excluded.pdf_s3_key,
            "updated_at":   datetime.now(tz=timezone.utc),
        }
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount == 1


def _enrich_from_pdf(bid: dict, keyword: str, log) -> dict:
    """Download and parse PDF for a bid. Returns enrichment dict (may be empty)."""
    pdf_download_url = bid.get("pdf_download_url", "")
    if not pdf_download_url:
        return {}

    bid_no = bid.get("bid_number", "N/A")
    pdf_label = bid_no if bid_no != "N/A" else f"{keyword}_{bid.get('gem_position', 0)}"

    time.sleep(random.uniform(1.0, 2.0))
    pdf_path = _download_pdf(pdf_download_url, pdf_label, settings.download_dir)
    if not pdf_path:
        log.warning("scrape_job.pdf_download_failed", bid_no=bid_no, url=pdf_download_url)
        return {}

    try:
        table_data, full_text = parse_pdf(pdf_path)
        extracted = extract_fields(
            table_data,
            full_text,
            bid_no=bid_no,
            dept_addr=bid.get("department", "N/A"),
            items_from_card=bid.get("items", "N/A"),
        )
    except Exception as exc:
        log.warning("scrape_job.pdf_parse_failed", bid_no=bid_no, error=str(exc))
        return {}

    def _val(key: str):
        v = extracted.get(key)
        return v if v and v != "N/A" else None

    enrichment = {
        "description":     _val("Category"),
        "cleaned_boq":     _val("Cleaned_BOQ"),
        "ministry":        _val("Ministry"),
        "tender_value":    _parse_amount(extracted.get("Bid_Value", "")),
        "emd":             _parse_amount(extracted.get("EMD", "")),
        "state":           _val("State"),
        "pincode":         _val("Pincode"),
        "delivery_period": _val("Delivery"),
        "product_type":    _val("Product_Type"),
        "exemption":       _val("Exemption"),
        "email":           _val("Email"),
    }

    buyer = _val("Buyer")
    if buyer:
        enrichment["organisation"] = buyer

    # Upload to S3/R2 (no-op if S3 not configured)
    s3_key = f"pdfs/{_safe_filename(bid_no)}.pdf"
    stored_key = upload_file_from_path(s3_key, pdf_path, content_type="application/pdf")
    if stored_key:
        enrichment["pdf_s3_key"] = stored_key

    log.debug("scrape_job.pdf_parsed", bid_no=bid_no, s3_key=stored_key)
    return enrichment


@celery_app.task(
    bind=True,
    name="tasks.scrape_job.run_scrape_job",
    max_retries=2,
    soft_time_limit=1800,
    time_limit=3600,
)
def run_scrape_job(self, job_id: int) -> dict:
    """Execute a GeM scraping job: direct API for order + PDF for full fields."""
    log = logger.bind(job_id=job_id, task_id=self.request.id)
    log.info("scrape_job.started")

    with Session(_engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            log.error("scrape_job.job_not_found")
            return {"error": "job not found"}

        keywords: list[str] = job.keywords if isinstance(job.keywords, list) else []
        cards_per_kw: int = job.cards_per_kw or 10
        tenant_id: str = job.tenant_id
        sort_preference: str = job.sort_preference or "bid_end_latest"

        try:
            job.status = "running"
            job.started_at = datetime.now(tz=timezone.utc)
            job.total_keywords = len(keywords)
            job.done_keywords = 0
            job.total_tenders = 0
            session.commit()
            _publish_event(session, job_id, "status_change", {"status": "running"})

            total_tenders = 0

            for keyword in keywords:
                log.info("scrape_job.keyword_start", keyword=keyword)
                _publish_event(session, job_id, "keyword_start", {"keyword": keyword})

                # ── Fetch pages from GeM direct API ──────────────────────────
                all_bids: list[dict] = []
                page = 1
                while len(all_bids) < cards_per_kw:
                    result = scrape_gem_direct(
                        keyword=keyword,
                        sort=sort_preference,
                        page=page,
                    )
                    if result.get("error") or not result.get("bids"):
                        log.warning("scrape_job.fetch_empty", keyword=keyword, page=page,
                                    error=result.get("error"))
                        break
                    all_bids.extend(result["bids"])
                    if len(result["bids"]) < 10:
                        break  # last page on GeM
                    page += 1
                    if page > 1:
                        time.sleep(1)

                all_bids = all_bids[:cards_per_kw]

                # ── Process each bid ─────────────────────────────────────────
                inserted = 0
                for bid in all_bids:
                    bid_no  = bid.get("bid_number", "N/A")
                    pdf_url = bid.get("pdf_url", "")

                    tender_data: dict = {
                        "keyword":         keyword,
                        "gem_position":    bid.get("gem_position"),
                        "tender_ref_no":   bid_no,
                        "title":           bid.get("items"),
                        "quantity":        bid.get("quantity"),
                        "organisation":    bid.get("department"),
                        "published_date":  _str_to_date(bid.get("start_date", "")),
                        "bid_end_date":    _str_to_datetime(bid.get("end_date", "")),
                        "link":            bid.get("pdf_url"),
                        "scraped_date":    date.today(),
                        "tender_type":     None,
                        "description":     None,
                        "cleaned_boq":     None,
                        "ministry":        bid.get("ministry") or None,
                        "tender_value":    None,
                        "emd":             None,
                        "state":           None,
                        "pincode":         None,
                        "delivery_period": None,
                        "product_type":    None,
                        "exemption":       None,
                        "email":           None,
                        "it_relevant":     "NO",
                        "pdf_s3_key":      None,
                    }

                    # ── PDF download + extraction ─────────────────────────────
                    if pdf_url:
                        time.sleep(random.uniform(1.0, 2.0))
                        try:
                            import httpx as _httpx
                            _dl_headers = {
                                "User-Agent": (
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/120.0.0.0 Safari/537.36"
                                ),
                                "Referer": "https://bidplus.gem.gov.in/all-bids",
                            }
                            r = _httpx.get(
                                pdf_url, headers=_dl_headers, timeout=30, follow_redirects=True
                            )
                            ct = r.headers.get("content-type", "").lower()
                            if r.status_code == 200 and "pdf" in ct:
                                os.makedirs(settings.download_dir, exist_ok=True)
                                pdf_path = os.path.join(
                                    settings.download_dir, _safe_filename(bid_no) + ".pdf"
                                )
                                with open(pdf_path, "wb") as _f:
                                    _f.write(r.content)

                                table_data, full_text = parse_pdf(pdf_path)
                                extracted = extract_fields(
                                    table_data,
                                    full_text,
                                    bid_no=bid_no,
                                    dept_addr=bid.get("department", "N/A"),
                                    items_from_card=bid.get("items", "N/A"),
                                )

                                def _val(key: str):
                                    v = extracted.get(key)
                                    return v if v and v != "N/A" else None

                                tender_data["description"]     = _val("Category")
                                tender_data["cleaned_boq"]     = _val("Cleaned_BOQ")
                                tender_data["ministry"]        = _val("Ministry") or tender_data["ministry"]
                                tender_data["tender_value"]    = _parse_amount(extracted.get("Bid_Value", ""))
                                tender_data["emd"]             = _parse_amount(extracted.get("EMD", ""))
                                tender_data["state"]           = _val("State")
                                tender_data["pincode"]         = _val("Pincode")
                                tender_data["delivery_period"] = _val("Delivery")
                                tender_data["product_type"]    = _val("Product_Type")
                                tender_data["exemption"]       = _val("Exemption")
                                tender_data["email"]           = _val("Email")

                                buyer = _val("Buyer")
                                if buyer:
                                    tender_data["organisation"] = buyer

                                s3_key = f"pdfs/{_safe_filename(bid_no)}.pdf"
                                stored = upload_file_from_path(
                                    s3_key, pdf_path, content_type="application/pdf"
                                )
                                if stored:
                                    tender_data["pdf_s3_key"] = stored

                                log.debug("scrape_job.pdf_parsed", bid_no=bid_no, s3_key=stored)
                            else:
                                log.warning(
                                    "scrape_job.pdf_not_pdf",
                                    bid_no=bid_no,
                                    status=r.status_code,
                                    content_type=ct,
                                )
                        except Exception as exc:
                            log.warning("scrape_job.pdf_download_failed", bid_no=bid_no, error=str(exc))

                    # IT relevance (uses enriched data if available)
                    it_flag = is_it_relevant(
                        tender_data.get("title") or "",
                        tender_data.get("description") or "",
                        keyword,
                    )
                    tender_data["it_relevant"] = "YES" if it_flag else "NO"

                    try:
                        ok = _upsert_tender(session, job_id, tenant_id, tender_data)
                        if ok:
                            inserted += 1
                        _publish_event(session, job_id, "card_scraped",
                                       {"bid_no": bid_no, "count": inserted})
                    except Exception as exc:
                        log.warning("scrape_job.tender_insert_failed",
                                    bid_no=bid_no, error=str(exc))

                total_tenders += inserted
                job.done_keywords = (job.done_keywords or 0) + 1
                job.total_tenders = total_tenders
                session.commit()

                _publish_event(session, job_id, "keyword_done",
                               {"keyword": keyword, "count": inserted, "total": total_tenders})
                log.info("scrape_job.keyword_done", keyword=keyword, tenders_found=inserted)

                if keyword != keywords[-1]:
                    time.sleep(1)

            _publish_event(session, job_id, "complete", {"total_tenders": total_tenders})

            job.status = "completed"
            job.completed_at = datetime.now(tz=timezone.utc)
            session.commit()
            log.info("scrape_job.completed", total_tenders=total_tenders)

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
                fire_job_event.delay(
                    tenant_id=tenant_id,
                    event="job.failed",
                    payload={"job_id": job_id, "error": str(exc)},
                )
            except Exception:
                pass
            raise self.retry(exc=exc, countdown=30)
