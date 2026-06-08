"""Direct GeM portal proxy — fetches bids exactly as GeM shows them.

Uses GeM's internal JSON endpoint (`/all-bids-data`) which requires a
session cookie + CSRF token obtained from a preliminary GET to `/all-bids`.
No Playwright. No DB. No reordering.
"""

import json
import re
import threading
import time

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE = "https://bidplus.gem.gov.in"
_LIST_URL = f"{_BASE}/all-bids"
_DATA_URL = f"{_BASE}/all-bids-data"

# How long to reuse a cached session before refreshing (seconds)
_SESSION_TTL = 300

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# Maps our sort keys → GeM's sort string values
_SORT_MAP = {
    "bid_end_latest":   "Bid-End-Date-Latest",
    "bid_end_oldest":   "Bid-End-Date-Oldest",
    "bid_start_latest": "Bid-Start-Date-Latest",
    "bid_start_oldest": "Bid-Start-Date-Oldest",
    "gem_order":        "Bid-End-Date-Latest",
}

# Thread-safe session cache
_session_lock = threading.Lock()
_session_cache: dict = {}  # {"cookies": ..., "csrf": ..., "ts": float}


def _refresh_session(client: httpx.Client) -> str:
    """GET /all-bids, extract CSRF token from cookies/HTML, cache it."""
    resp = client.get(_LIST_URL, headers=_HEADERS, follow_redirects=True, timeout=20)
    resp.raise_for_status()

    # CSRF token from cookie (preferred)
    csrf = client.cookies.get("csrf_gem_cookie", "")

    # Fallback: grep from inline JS
    if not csrf:
        m = re.search(r"csrf_bd_gem_nk['\"]?\s*:\s*['\"]([a-f0-9]{32})['\"]", resp.text)
        if m:
            csrf = m.group(1)

    if not csrf:
        logger.warning("gem_proxy.csrf_not_found")

    return csrf


def _get_session() -> tuple[dict, str]:
    """Return (cookies_dict, csrf_token), refreshing if stale."""
    with _session_lock:
        now = time.monotonic()
        if _session_cache and now - _session_cache.get("ts", 0) < _SESSION_TTL:
            return _session_cache["cookies"], _session_cache["csrf"]

    with httpx.Client(timeout=25, follow_redirects=True) as client:
        csrf = _refresh_session(client)
        cookies = dict(client.cookies)

    with _session_lock:
        _session_cache.update({"cookies": cookies, "csrf": csrf, "ts": time.monotonic()})

    return cookies, csrf


def _invalidate_session() -> None:
    with _session_lock:
        _session_cache.clear()


def _call_data_endpoint(
    keyword: str,
    sort: str,
    page: int,
    cookies: dict,
    csrf: str,
) -> dict:
    payload = {
        "page": page,
        "param": {
            "searchBid": keyword,
            "searchType": "contains",
        },
        "filter": {
            "bidStatusType": "ongoing_bids",
            "byType": "all",
            "highBidValue": "",
            "byEndDate": {"from": "", "to": ""},
            "sort": _SORT_MAP.get(sort, "Bid-End-Date-Latest"),
        },
    }

    post_data = {
        "payload": json.dumps(payload, separators=(",", ":")),
        "csrf_bd_gem_nk": csrf,
    }

    headers = {
        **_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": _LIST_URL,
        "Origin": _BASE,
    }

    with httpx.Client(cookies=cookies, timeout=25, follow_redirects=True) as client:
        resp = client.post(_DATA_URL, data=post_data, headers=headers)
        resp.raise_for_status()

    return resp.json()


def _parse_date(raw: str | None) -> str:
    """Convert Solr ISO datetime to DD/MM/YYYY or return as-is."""
    if not raw:
        return "N/A"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T", raw)
    if m:
        y, mo, d = m.groups()
        return f"{d}/{mo}/{y}"
    return raw


def scrape_gem_direct(
    keyword: str,
    sort: str = "bid_end_latest",
    page: int = 1,
) -> dict:
    """
    Fetch bids from GeM portal exactly as they appear.
    Returns bids in GeM's exact order — no reordering applied.
    10 results per page (server-side fixed).
    """
    cookies, csrf = _get_session()

    try:
        data = _call_data_endpoint(keyword, sort, page, cookies, csrf)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 401):
            # CSRF expired — force refresh and retry once
            logger.info("gem_proxy.csrf_expired_retrying")
            _invalidate_session()
            cookies, csrf = _get_session()
            try:
                data = _call_data_endpoint(keyword, sort, page, cookies, csrf)
            except Exception as inner:
                logger.error("gem_proxy.retry_failed", error=str(inner))
                return _error_response(keyword, sort, page, str(inner))
        else:
            logger.error("gem_proxy.http_error", status=exc.response.status_code)
            return _error_response(keyword, sort, page, str(exc))
    except Exception as exc:
        logger.error("gem_proxy.fetch_failed", error=str(exc))
        return _error_response(keyword, sort, page, str(exc))

    # Validate response shape
    if not isinstance(data, dict) or data.get("status") != 1:
        msg = data.get("message", "Unknown error") if isinstance(data, dict) else "Bad response"
        logger.warning("gem_proxy.bad_status", message=msg)
        return _error_response(keyword, sort, page, msg)

    try:
        solr = data["response"]["response"]
        docs = solr.get("docs", [])
        total = solr.get("numFound", 0)
    except (KeyError, TypeError) as exc:
        logger.error("gem_proxy.parse_failed", error=str(exc))
        return _error_response(keyword, sort, page, str(exc))

    start_position = (page - 1) * 10 + 1
    bids = []
    for i, doc in enumerate(docs):
        def first(val):
            if isinstance(val, list):
                return val[0] if val else ""
            return val or ""

        bid_number = first(doc.get("b_bid_number", ""))
        bid_id     = doc.get("id", "")   # numeric Solr ID → used in /bidlisting/{id}
        start_date = _parse_date(first(doc.get("final_start_date_sort")))
        end_date   = _parse_date(first(doc.get("final_end_date_sort")))
        items      = first(doc.get("b_category_name") or doc.get("bd_category_name", ""))
        quantity   = str(first(doc.get("b_total_quantity", "")))
        department = first(doc.get("ba_official_details_deptName", ""))
        ministry   = first(doc.get("ba_official_details_minName", ""))

        gem_url = f"https://bidplus.gem.gov.in/bidlisting/{bid_id}" if bid_id else ""
        pdf_url = f"https://bidplus.gem.gov.in/showbidDocument/{bid_id}" if bid_id else ""

        bids.append({
            "gem_position": start_position + i,
            "bid_number":   bid_number,
            "bid_id":       bid_id,
            "items":        items,
            "quantity":     quantity,
            "department":   department,
            "ministry":     ministry,
            "start_date":   start_date,
            "end_date":     end_date,
            "pdf_url":      pdf_url,
            "gem_url":      gem_url,
            "bid_url":      pdf_url,
        })

    logger.info("gem_proxy.done", keyword=keyword, found=len(bids), total=total, page=page)
    return {
        "bids":    bids,
        "total":   total,
        "page":    page,
        "keyword": keyword,
        "sort":    sort,
    }


def _error_response(keyword: str, sort: str, page: int, error: str) -> dict:
    return {"bids": [], "total": 0, "page": page, "keyword": keyword, "sort": sort, "error": error}
