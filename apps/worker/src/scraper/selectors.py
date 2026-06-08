"""GeM portal selectors — all CSS/XPath selectors in one place.

When GeM changes their DOM, only this file needs updating.
"""

BASE_URL = "https://bidplus.gem.gov.in/all-bids"
BID_BASE_URL = "https://bidplus.gem.gov.in"

# CSS selectors
SEARCH_INPUT = "#searchBid"
BID_CARDS = ".block_header"
BID_NO_LINK = "a.bid_no_hover"

# XPath selectors (Playwright uses page.locator("xpath=...") or page.locator("//..."))
SORT_DROPDOWN = (
    "//button[contains(@class,'dropdown-toggle') and "
    "(contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sort'))]"
)
SORT_LATEST = (
    "//a[contains(text(),'Bid End Date: Latest First')] | "
    "//li[contains(text(),'Bid End Date: Latest First')]"
)
SORT_BID_END_OLDEST = (
    "//a[contains(text(),'Bid End Date: Oldest First')] | "
    "//li[contains(text(),'Bid End Date: Oldest First')]"
)
SORT_BID_START_LATEST = (
    "//a[contains(text(),'Bid Start Date: Latest First')] | "
    "//li[contains(text(),'Bid Start Date: Latest First')] | "
    "//a[contains(text(),'Published Date: Latest')] | "
    "//li[contains(text(),'Published Date: Latest')]"
)
SORT_BID_START_OLDEST = (
    "//a[contains(text(),'Bid Start Date: Oldest First')] | "
    "//li[contains(text(),'Bid Start Date: Oldest First')] | "
    "//a[contains(text(),'Published Date: Oldest')] | "
    "//li[contains(text(),'Published Date: Oldest')]"
)

# Maps the sort_preference string (stored on Job) to the GeM UI selector.
# If a selector does not match on the live portal, _sort_results() falls back
# to bid_end_latest (the only option verified against GeM's current DOM).
GEM_SORT_SELECTORS: dict[str, str] = {
    "bid_end_latest":   SORT_LATEST,
    "bid_end_oldest":   SORT_BID_END_OLDEST,
    "bid_start_latest": SORT_BID_START_LATEST,
    "bid_start_oldest": SORT_BID_START_OLDEST,
}
CLOSE_MODAL = "//button[contains(text(),'Close')]"
NEXT_PAGE = "//a[normalize-space()='Next' and not(contains(@class,'disabled'))]"

# User-agent for PDF downloads
DOWNLOAD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DOWNLOAD_HEADERS = {
    "User-Agent": DOWNLOAD_UA,
    "Referer": BASE_URL,
    "Accept": "application/pdf,*/*",
}
