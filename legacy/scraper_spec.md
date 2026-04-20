# GeM Scraper Specification
## Recovered from GeM_Tender_Bot.exe — READ ONLY REFERENCE

> Source files recovered intact from PyInstaller bundle (Python 3.14).
> All 6 modules bundled as plain .py files, not compiled.
> Use this as the authoritative spec for the Playwright rewrite.

---

## URLs

| Purpose | URL |
|---|---|
| Entry point / search | `https://bidplus.gem.gov.in/all-bids` |
| Bid card href base | `https://bidplus.gem.gov.in` + relative href |
| PDF download | href from `a.bid_no_hover` — direct HTTP GET with browser headers |

---

## Selenium Selectors (source) → Playwright Equivalents

| Element | Legacy (Selenium) | Playwright |
|---|---|---|
| Search input | `By.ID, "searchBid"` | `#searchBid` |
| Bid result cards | `By.CLASS_NAME, "block_header"` | `.block_header` |
| PDF / bid link | `By.CSS_SELECTOR, "a.bid_no_hover"` | `a.bid_no_hover` |
| Sort dropdown | `//button[contains(@class,'dropdown-toggle') and contains(text(),'sort')]` | XPath locator |
| Sort option | `contains(text(),'Bid End Date: Latest First')` | XPath locator |
| Close popup btn | `//button[contains(text(),'Close')]` | XPath locator |
| Pagination next | `//a[normalize-space()='Next' and not(contains(@class,'disabled'))]` | XPath locator |

---

## Card Text Structure

GeM renders each `.block_header` card as multi-line text. Parent element `.text` looks like:

```
Bid No.: GEM/2026/B/7424230
Items: Laptop, Workstation
Quantity: 50
Department Name And Address:
Ministry of Education
University of Delhi
Start Date: 28-03-2026 5:00 PM
End Date: 15-04-2026 5:00 PM
```

**Parsing logic (from `main.py:parse_card_text`):**
- `Bid_No`: regex `r'Bid\s+No\.?\s*:\s*(GEM/[\w/]+)'`
- `Items`: line after `"Items:"`
- `Quantity`: line after `"Quantity:"`
- `Dept_Addr`: next 2 lines after `"Department Name And Address:"`
- `Start_Date`: line after `"Start Date:"`
- `End_Date`: line after `"End Date:"`

**Tender type inference** (from card text):
- `"boq"` → contains: boq, bill of quantity
- `"service"` → contains: service bid, service ra
- `"product_custom"` → contains: custom bid, custom product
- `"product"` → default

---

## PDF Download

From `downloader.py`:
```python
BASE_URL = "https://bidplus.gem.gov.in/all-bids"
HEADERS = {
    "User-Agent": "Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
    "Accept": "application/pdf,*/*",
}
requests.get(url, headers=HEADERS, timeout=30, stream=True)
```

Filename: `safe_filename(bid_id) + ".pdf"` where `safe_filename` replaces `[\\/*?:"<>|]` with `_`

---

## PDF Parsing

From `pdf_parser.py` (uses `pdfplumber`):
```python
table_settings = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
}
```
- Tables: two-column layout (label | value), first cell = key, last cell = value
- Text: full text extraction, Devanagari stripped, CID junk removed

---

## 23-Column XLSX Mapping

From `main.py:run()` → `final_rows.append({...})`:

| XLSX Column | Source Field | Source |
|---|---|---|
| S.No | sequential index | computed |
| Keyword | `Keyword` | search keyword |
| Tender Reference No | `Bid_No` | card text regex |
| Tender Type | `Tender_Type` | card text inference |
| Published Date | `Start_Date` | card text |
| Bid Submission End Date | `End_Date` | card text |
| Title | `Items` | card text |
| Description | `Category` or `Items` | PDF extractor |
| Cleaned BOQ | `Cleaned_BOQ` | PDF extractor |
| Organisation | `Buyer` or `Dept_Addr[0]` | PDF extractor + card fallback |
| Ministry | `Ministry` | PDF extractor |
| Tender Value | `Bid_Value` | PDF extractor |
| EMD | `EMD` | PDF extractor |
| State | `State` | PDF extractor |
| Pincode | `Pincode` | PDF extractor |
| Delivery Period | `Delivery` | PDF extractor |
| Product Type | `Product_Type` | PDF extractor |
| Exemption | `Exemption` | PDF extractor |
| Email | `Email` | PDF extractor |
| IT Relevant | `IT_Relevant` | `is_it_relevant()` |
| Quantity | `Quantity` | card text |
| Link | `PDF_URL` | card href |
| Scraped Date | `Scraped_At` | `datetime.now()` |

**XLSX format:**
- Row 1: merged date-range title — `"Tenders Published: {start} to {end}"` (dark blue `#1F4E79`, white bold)
- Row 2: column headers (blue `#2E75B6`, white bold, center-aligned, wrap)
- Row 3+: data rows
- Two sheets: `"All Tenders"` and `"IT Relevant Only"`
- Column widths: auto (max content + 4), capped at 60; BOQ/Description fixed at 50

---

## FIELD_MAP (PDF table key → internal field name)

From `extractor.py:FIELD_MAP`:

| Internal Field | PDF Table Keys Searched |
|---|---|
| Ministry | ministry/state name, ministry name, ministry |
| Buyer | organisation name, buyer name, consignee name, buyer |
| Bid_Value | estimated bid value, bid value, tender value |
| EMD | emd amount, earnest money deposit, bid security |
| Delivery | delivery period in days, contract period, delivery period |
| Category | item category, product category, category name |
| Exemption | mse relaxation..., startup relaxation..., mse exemption |
| Email | email id, email address, e-mail |
| Pincode | pin code, pincode, postal code |
| State | ministry/state name, state name, state of delivery |
| Product_Type | type of bid, bid type, product type |

---

## IT Relevance Logic

From `extractor.py`:
- First check `NON_IT_KEYWORDS` → if any match → return `False`
- Then check `IT_KEYWORDS` → if any match → return `True`
- Default: `True`

Key IT keywords: server, laptop, desktop, workstation, amc, camc, fms, networking, firewall, hpc, software, cloud, data center, storage, router, switch, cyber, cctv, erp, computer, printer, scanner, ups, wifi

---

## Stealth Configuration

From `scraper.py:get_driver()`:
```python
stealth(driver,
    languages=["en-US", "en"],
    vendor="Google Inc.",
    platform="Win32",
    webgl_vendor="Intel Inc.",
    renderer="Intel Iris OpenGL Engine",
    fix_hairline=True,
)
```
Playwright equivalent: `playwright-stealth` with `stealth_sync(page)`.

---

## Run Config

From `main.py`:
- `CARDS_PER_KEYWORD = 2` (default; golden run used 3)
- `MIN_VALUE = 50000` (skip tenders below ₹50,000)
- Sort by: `Bid End Date: Latest First`
- Dedup key: `bid_no` if available, else `pdf_url`
