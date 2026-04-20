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
