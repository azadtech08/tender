"""GemScraper — Playwright-based scraper for bidplus.gem.gov.in.

Uses sync_playwright (Celery tasks are synchronous).
Selectors isolated in selectors.py — update there when GeM changes DOM.
"""

import os
import re
import random
import time
from datetime import date, datetime
from typing import Callable, Optional

import requests
import structlog
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
from playwright_stealth import Stealth

from .selectors import (
    BASE_URL, BID_BASE_URL,
    SEARCH_INPUT, BID_CARDS, BID_NO_LINK,
    SORT_DROPDOWN, SORT_LATEST, CLOSE_MODAL, NEXT_PAGE,
    DOWNLOAD_HEADERS, GEM_SORT_SELECTORS,
)
from .pdf_extractor import parse_pdf, extract_fields, is_it_relevant
from utils.s3 import upload_file_from_path

logger = structlog.get_logger(__name__)

# Safety cap — pagination stops here even if the caller's target is not met.
# Prevents a runaway scrape on a huge result set or a broken Next button loop.
MAX_PAGES = 100

# ── Card text parsers ─────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _parse_bid_no(text: str) -> str:
    m = re.search(r"Bid\s+No\.?\s*:\s*(GEM/[\w/]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(GEM/\d{4}/[A-Z]/\d+)\b", text)
    return m.group(1).strip() if m else "N/A"


def _parse_tender_type(text: str) -> str:
    tl = text.lower()
    if any(k in tl for k in ("boq", "bill of quantity")):
        return "boq"
    if any(k in tl for k in ("service bid", "service ra", "service contract")):
        return "service"
    if any(k in tl for k in ("custom bid", "custom product", "customized")):
        return "product_custom"
    return "product"


def _parse_card_text(text: str) -> dict:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    fields: dict[str, str] = {
        "Bid_No": _parse_bid_no(text),
        "Tender_Type": _parse_tender_type(text),
        "Start_Date": "N/A",
        "End_Date": "N/A",
        "Dept_Addr": "N/A",
        "Items": "N/A",
        "Quantity": "N/A",
    }
    for i, line in enumerate(lines):
        if "Items:" in line:
            fields["Items"] = line.replace("Items:", "").strip()
        elif "Quantity:" in line:
            fields["Quantity"] = line.replace("Quantity:", "").strip()
        elif "Department Name And Address:" in line:
            fields["Dept_Addr"] = " | ".join(lines[i + 1: i + 3])
        elif "Start Date:" in line:
            fields["Start_Date"] = line.replace("Start Date:", "").strip()
        elif "End Date:" in line:
            fields["End_Date"] = line.replace("End Date:", "").strip()
    return fields


def _parse_date(s: str) -> Optional[date]:
    """Parse GeM date strings like '28-03-2026 5:00 PM' or '28-03-2026'."""
    if not s or s == "N/A":
        return None
    for fmt in ("%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime as dt
            return dt.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(s: str):
    """Parse GeM datetime strings into datetime or None."""
    if not s or s == "N/A":
        return None
    from datetime import datetime as dt, timezone
    for fmt in ("%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            naive = dt.strptime(s.strip(), fmt)
            return naive.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_amount(val: str) -> Optional[float]:
    if not val or val == "N/A":
        return None
    try:
        return float(val.replace(",", "").strip())
    except ValueError:
        return None


# ── PDF download ──────────────────────────────────────────────────────────────

def _download_pdf(url: str, bid_id: str, download_dir: str) -> Optional[str]:
    os.makedirs(download_dir, exist_ok=True)
    path = os.path.join(download_dir, _safe_filename(bid_id) + ".pdf")
    if os.path.exists(path):
        return path
    try:
        resp = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in resp.iter_content(8192):
                fh.write(chunk)
        return path
    except Exception as exc:
        logger.warning("pdf.download_failed", url=url, error=str(exc))
        return None


# ── Browser helpers ───────────────────────────────────────────────────────────

def _dismiss_modal(page: Page) -> None:
    try:
        btn = page.locator(CLOSE_MODAL).first
        if btn.is_visible(timeout=3000):
            btn.click()
            time.sleep(0.5)
    except Exception:
        pass


def _sort_results(page: Page, sort_pref: str = "bid_end_latest") -> None:
    selector = GEM_SORT_SELECTORS.get(sort_pref, SORT_LATEST)
    try:
        toggle = page.locator(SORT_DROPDOWN).first
        toggle.click()
        time.sleep(1)
        option = page.locator(selector).first
        if not option.is_visible(timeout=2000):
            # Selector not found on live GeM — fall back to the proven default
            logger.debug("sort.option_not_found", sort_pref=sort_pref, fallback="bid_end_latest")
            page.locator(SORT_LATEST).first.click()
        else:
            option.click()
        time.sleep(random.uniform(3, 5))
        page.wait_for_selector(BID_CARDS, timeout=10000)
    except Exception as exc:
        logger.debug("sort.failed", error=str(exc))


def _advance_page(page: Page, log) -> bool:
    """Click the Next pagination link and wait for the following results page to load.

    Returns True if navigation succeeded; False if Next is missing, disabled, or timed out.
    """
    try:
        btn = page.locator(NEXT_PAGE).first
        if not btn.is_visible(timeout=3000):
            return False
    except Exception:
        return False
    try:
        btn.scroll_into_view_if_needed()
        btn.click()
        time.sleep(random.uniform(2, 4))
        page.wait_for_selector(BID_CARDS, timeout=10000)
        return True
    except Exception as exc:
        log.warning("scraper.next_page_failed", error=str(exc))
        return False


def _collect_cards_with_position(
    page: Page, limit: int, start_position: int = 1
) -> list[dict]:
    """Collect up to `limit` bid card dicts and assign gem_position at collection time.

    start_position lets page 2, 3... continue numbering from where page 1 left off.
    """
    collected: list[dict] = []
    seen: set[str] = set()
    current_position = start_position  # continues across pages

    for _attempt in range(3):
        cards = page.locator(BID_CARDS).all()
        for card in cards:
            if len(collected) >= limit:
                break
            try:
                parent = card.locator("xpath=..").first
                text = parent.inner_text()
                href = ""
                try:
                    href = card.locator(BID_NO_LINK).first.get_attribute("href") or ""
                except Exception:
                    try:
                        href = parent.locator(BID_NO_LINK).first.get_attribute("href") or ""
                    except Exception:
                        pass
                if href and not href.startswith("http"):
                    href = BID_BASE_URL + href
                key = href if href else text[:200]
                if key and key not in seen:
                    seen.add(key)
                    collected.append({
                        "text":         text,
                        "pdf_url":      href or "N/A",
                        "gem_position": current_position,  # locked at collection time
                    })
                    current_position += 1
            except Exception:
                continue
        if len(collected) >= limit:
            break
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

    return collected


# ── Main scraper class ────────────────────────────────────────────────────────

class GemScraper:
    """Playwright-based scraper for GeM bidplus portal.

    Usage (inside a Celery task):
        scraper = GemScraper(headless=settings.headless, download_dir=settings.download_dir)
        tenders = scraper.scrape_keyword(keyword, cards_per_kw=3, min_value=50000, on_event=cb)
    """

    def __init__(self, headless: bool = True, download_dir: str = "/tmp/gem_pdfs") -> None:
        self.headless = headless
        self.download_dir = download_dir

    def _search_and_collect(
        self,
        keyword: str,
        cards_per_kw: int,
        log,
        _emit: Callable,
        sort_pref: str = "bid_end_latest",
    ) -> list[dict]:
        """Launch a browser, search for keyword, and return raw card dicts.

        Returns collected cards on success, raises on failure.
        """
        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=self.headless)
            try:
                context: BrowserContext = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                )
                page: Page = context.new_page()
                Stealth().apply_stealth_sync(page)

                log.info("scraper.navigate", url=BASE_URL)
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(2, 3))

                _dismiss_modal(page)

                # Search
                search = page.locator(SEARCH_INPUT).first
                search.scroll_into_view_if_needed()
                search.click()
                time.sleep(0.3)
                for char in keyword:
                    search.type(char, delay=random.randint(50, 150))
                search.press("Enter")
                time.sleep(random.uniform(5, 7))
                page.wait_for_selector(BID_CARDS, timeout=20000)
                log.info("scraper.results_loaded")

                _sort_results(page, sort_pref)

                # Accumulate unique cards across pages; stop as soon as the
                # user's requested count is met or we run out of pages.
                all_cards: list[dict] = []
                seen_keys: set[str] = set()

                def _absorb(fresh: list[dict]) -> int:
                    added = 0
                    for c in fresh:
                        url = c.get("pdf_url") or ""
                        key = url if url and url != "N/A" else c.get("text", "")[:200]
                        if key and key not in seen_keys:
                            seen_keys.add(key)
                            all_cards.append(c)
                            added += 1
                    return added

# Page 1
                global_position = 1  # absolute position counter across all pages
                page_cards = _collect_cards_with_position(
                    page, limit=cards_per_kw, start_position=global_position
                )
                _absorb(page_cards)
                global_position = len(all_cards) + 1  # next page continues from here
                log.info(
                    "scraper.cards_collected",
                    count=len(all_cards),
                    page=1,
                    target=cards_per_kw,
                )
                _emit(
                    "cards_found",
                    {"keyword": keyword, "count": len(page_cards), "page": 1},
                )

                # Subsequent pages — one click at a time, stop as soon as target met.
                current_page = 1
                while len(all_cards) < cards_per_kw and current_page < MAX_PAGES:
                    if not _advance_page(page, log):
                        log.info(
                            "scraper.no_more_pages",
                            collected=len(all_cards),
                            target=cards_per_kw,
                            stopped_at=current_page,
                        )
                        break
                    current_page += 1
                    remaining  = cards_per_kw - len(all_cards)
                    page_cards = _collect_cards_with_position(
                        page, limit=remaining, start_position=global_position
                    )
                    _absorb(page_cards)
                    global_position = len(all_cards) + 1  # update for next page
                    log.info(
                        "scraper.cards_collected",
                        count=len(page_cards),
                        page=current_page,
                        total=len(all_cards),
                        target=cards_per_kw,
                    )
                    _emit(
                        "cards_found",
                        {
                            "keyword": keyword,
                            "count": len(page_cards),
                            "page": current_page,
                        },
                    )

                return all_cards
            finally:
                browser.close()

    def scrape_keyword(
        self,
        keyword: str,
        cards_per_kw: int = 3,
        min_value: Optional[float] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
        sort_pref: str = "bid_end_latest",
    ) -> list[dict]:
        """Scrape one keyword from GeM and return tender dicts.

        Each dict maps directly to Tender model fields.
        Failures on individual cards are logged and skipped — not raised.
        """
        log = logger.bind(keyword=keyword, cards_per_kw=cards_per_kw)
        log.info("scraper.keyword_start")

        def _emit(event_type: str, payload: dict) -> None:
            if on_event:
                try:
                    on_event(event_type, payload)
                except Exception:
                    pass

        results: list[dict] = []

        # Attempt search with one retry using a fresh browser
        max_attempts = 2
        cards: list[dict] = []
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                cards = self._search_and_collect(keyword, cards_per_kw, log, _emit, sort_pref)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                log.warning(
                    "scraper.search_failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(exc),
                )
                if attempt < max_attempts:
                    backoff = random.uniform(5, 10)
                    log.info("scraper.search_retry", backoff=backoff)
                    _emit("search_retry", {"keyword": keyword, "attempt": attempt, "error": str(exc)})
                    time.sleep(backoff)

        if last_error is not None:
            log.error("scraper.search_exhausted", error=str(last_error))
            _emit("search_failed", {"keyword": keyword, "error": str(last_error)})
            return results

        # Process each card (browser already closed — only PDF downloads + parsing)
        for card in cards:
            try:
                cf = _parse_card_text(card["text"])
                pdf_url = card["pdf_url"]
                bid_no  = cf["Bid_No"]
                gem_pos = card["gem_position"]  # set at collection time — never reassign

                log.info("scraper.card_processing", bid_no=bid_no, gem_position=gem_pos)
                _emit("card_scraped", {"keyword": keyword, "bid_no": bid_no, "gem_position": gem_pos})

                tender: dict = {
                    "keyword": keyword,
                    "gem_position": gem_pos,
                    "tender_ref_no": bid_no,
                    "tender_type": cf["Tender_Type"],
                    "published_date": _parse_date(cf["Start_Date"]),
                    "bid_end_date": _parse_datetime(cf["End_Date"]),
                    "title": cf["Items"] if cf["Items"] != "N/A" else None,
                    "quantity": cf["Quantity"] if cf["Quantity"] != "N/A" else None,
                    "link": pdf_url if pdf_url != "N/A" else None,
                    "scraped_date": date.today(),
                    # PDF-extracted fields (filled below)
                    "description": None,
                    "cleaned_boq": None,
                    "organisation": None,
                    "ministry": None,
                    "tender_value": None,
                    "emd": None,
                    "state": None,
                    "pincode": None,
                    "delivery_period": None,
                    "product_type": None,
                    "exemption": None,
                    "email": None,
                    "it_relevant": None,
                    "pdf_s3_key": None,
                }

                # Download + parse PDF
                if pdf_url and pdf_url != "N/A":
                    time.sleep(random.uniform(1, 2))
                    pdf_label = bid_no if bid_no != "N/A" else f"{keyword}_{i}"
                    pdf_path = _download_pdf(pdf_url, pdf_label, self.download_dir)

                    if pdf_path:
                        table_data, full_text = parse_pdf(pdf_path)
                        extracted = extract_fields(
                            table_data, full_text,
                            bid_no=bid_no,
                            dept_addr=cf["Dept_Addr"],
                            items_from_card=cf["Items"],
                        )

                        tender["description"] = (
                            extracted.get("Category") if extracted.get("Category") != "N/A" else None
                        )
                        tender["cleaned_boq"] = (
                            extracted["Cleaned_BOQ"] if extracted["Cleaned_BOQ"] != "N/A" else None
                        )
                        tender["ministry"] = (
                            extracted["Ministry"] if extracted["Ministry"] != "N/A" else None
                        )
                        tender["tender_value"] = _parse_amount(extracted.get("Bid_Value"))
                        tender["emd"] = _parse_amount(extracted.get("EMD"))
                        tender["state"] = (
                            extracted["State"] if extracted["State"] != "N/A" else None
                        )
                        tender["pincode"] = (
                            extracted["Pincode"] if extracted["Pincode"] != "N/A" else None
                        )
                        tender["delivery_period"] = (
                            extracted["Delivery"] if extracted["Delivery"] != "N/A" else None
                        )
                        tender["product_type"] = (
                            extracted["Product_Type"] if extracted["Product_Type"] != "N/A" else None
                        )
                        tender["exemption"] = (
                            extracted["Exemption"] if extracted["Exemption"] != "N/A" else None
                        )
                        tender["email"] = (
                            extracted["Email"] if extracted["Email"] != "N/A" else None
                        )
     
                        buyer = extracted.get("Buyer", "N/A")
                        if buyer != "N/A":
                            tender["organisation"] = buyer
                        elif cf["Dept_Addr"] != "N/A":
                            tender["organisation"] = cf["Dept_Addr"].split("|")[0].strip()

                        # Upload PDF to S3/R2 (no-op if S3 not configured)
                        s3_key = f"pdfs/{_safe_filename(bid_no)}.pdf"
                        stored_key = upload_file_from_path(
                            s3_key, pdf_path, content_type="application/pdf"
                        )
                        if stored_key:
                            tender["pdf_s3_key"] = stored_key

                        _emit("pdf_parsed", {"bid_no": bid_no, "pdf_path": pdf_path, "s3_key": stored_key})
                    else:
                        log.warning("scraper.pdf_download_failed", bid_no=bid_no)

                # IT relevance
                it_flag = is_it_relevant(
                    tender.get("title") or "",
                    tender.get("description") or "",
                    keyword,
                )
                tender["it_relevant"] = "YES" if it_flag else "NO"

                # Min value filter
                if min_value is not None and tender["tender_value"] is not None:
                    if tender["tender_value"] < min_value:
                        log.info(
                            "scraper.tender_filtered",
                            bid_no=bid_no,
                            value=tender["tender_value"],
                            min_value=min_value,
                        )
                        continue

                results.append(tender)
                time.sleep(random.uniform(0.5, 1.5))  # ≤1 req/sec

            except Exception as exc:
                log.warning("scraper.card_failed", i=i, error=str(exc))
                continue

        # Preserve GeM portal order — do NOT re-sort.
        # gem_position (1-based) was captured from the card index during collection
        # and reflects the order GeM returned after applying sort_pref on the portal.
        # Truncate only if the min_value filter produced more than requested.
        

        log.info("scraper.keyword_done", tenders_found=len(results))
        return results
