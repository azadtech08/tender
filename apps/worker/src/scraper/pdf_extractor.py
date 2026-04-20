"""PDF extractor — parses GeM bid PDFs into structured field dicts.

Logic ported from legacy/decompiled/pdf_parser.py + extractor.py.
"""

import re
from typing import Optional

import pdfplumber


# ── Text helpers ──────────────────────────────────────────────────────────────

def clean_text(text) -> str:
    if not text:
        return ""
    text = str(text)
    text = re.sub(r"[\u0900-\u097F]", "", text)   # strip Devanagari
    text = re.sub(r"\(cid:\d+\)", "", text)         # remove CID junk
    text = re.sub(r"^\s*/\s*|\s*/\s*$", "", text)
    return re.sub(r"\s+", " ", text).strip()


# ── PDF parser ────────────────────────────────────────────────────────────────

_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
}


def parse_pdf(file_path: str) -> tuple[dict, str]:
    """Extract table data and full text from a GeM bid PDF.

    Returns:
        (table_data, full_text) where table_data is a flat {label: value} dict
        derived from two-column PDF tables, and full_text is cleaned plain text.
    """
    table_data: dict[str, str] = {}
    raw_text = ""

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables(_TABLE_SETTINGS):
                    for row in table:
                        if not row:
                            continue
                        cells = [clean_text(c) for c in row if c and clean_text(c)]
                        if len(cells) < 2:
                            continue
                        key = cells[0].lower().strip()
                        value = cells[-1].strip()
                        if len(key) < 3 or len(key) > 100 or re.fullmatch(r"[\d\s₹,\.]+", key):
                            continue
                        table_data.setdefault(key, value)
                        # Also index interior cell pairs
                        for i in range(len(cells) - 1):
                            k = cells[i].lower().strip()
                            v = cells[i + 1].strip()
                            if 3 <= len(k) <= 100 and not re.fullmatch(r"[\d\s₹,\.]+", k):
                                table_data.setdefault(k, v)

            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    raw_text += clean_text(t) + "\n"

    except Exception:
        pass  # Caller handles empty returns

    full_text = re.sub(r"\s+", " ", raw_text).strip()
    return table_data, full_text


# ── Field mapping ─────────────────────────────────────────────────────────────

_FIELD_MAP: dict[str, list[str]] = {
    "Ministry":     ["ministry/state name", "ministry name", "ministry"],
    "Buyer":        ["organisation name", "buyer organisation name", "buyer name", "consignee name", "buyer"],
    "Bid_Value":    ["estimated bid value", "estimated value in inr", "bid value", "tender value"],
    "EMD":          ["emd amount", "earnest money deposit", "bid security amount", "emd"],
    "Delivery":     ["delivery period in days", "delivery period (in days)", "delivery period", "contract period"],
    "Category":     ["item category", "product category", "category name", "category"],
    "Exemption":    ["mse relaxation for years of experience and turnover", "mse exemption", "startup exemption", "exemption"],
    "Email":        ["email id", "email address", "e-mail", "email"],
    "Pincode":      ["pin code", "pincode", "postal code"],
    "State":        ["state name", "state of delivery", "consignee state", "state"],
    "Product_Type": ["type of bid", "bid type", "product type"],
}

_JUNK = {"yes", "no", "download", "n/a", "na", "-", "none", "null", ""}

_VALID_PIN_PREFIXES = {
    "11","12","13","14","15","16","17","18","19",
    "20","21","22","23","24","25","26","27","28","29",
    "30","31","32","33","34","36","37","38","39",
    "40","41","42","43","44","45","46","47","48","49",
    "50","51","52","53","56","57","58","60","61","62",
    "63","64","67","68","69","70","71","72","73","74",
    "75","76","77","78","79","80","81","82","83","84","85","86",
}

_INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi",
    "Jammu & Kashmir", "Ladakh", "Chandigarh", "Puducherry",
]


def _find_value(data: dict, patterns: list[str]) -> str:
    for pat in patterns:
        for k, v in data.items():
            if k.strip().lower() == pat.lower():
                val = str(v).strip()
                if val.lower() not in _JUNK and len(val) > 1:
                    return val
    for pat in patterns:
        for k, v in data.items():
            if pat.lower() in k.strip().lower():
                val = str(v).strip()
                if val.lower() not in _JUNK and len(val) > 1:
                    return val
    return "N/A"


def _is_valid_pincode(s: str) -> bool:
    if not re.fullmatch(r"\d{6}", s) or s[0] == "0":
        return False
    return s[:2] in _VALID_PIN_PREFIXES


def _clean_amount(val: str) -> str:
    try:
        return str(int(float(val.strip().replace(",", ""))))
    except ValueError:
        return val


# ── Main extractor ────────────────────────────────────────────────────────────

def extract_fields(
    table_data: dict,
    full_text: str,
    bid_no: str = "",
    dept_addr: str = "",
    items_from_card: str = "",
) -> dict:
    """Extract all 23-column fields from parsed PDF data.

    Args:
        table_data: Flat {label: value} dict from parse_pdf()
        full_text:  Full cleaned text from parse_pdf()
        bid_no:     Bid number from card HTML (for context)
        dept_addr:  Department address string from card HTML (Buyer fallback)
        items_from_card: Items string from card HTML (BOQ fallback)

    Returns:
        Dict with keys matching _FIELD_MAP plus Cleaned_BOQ.
    """
    result = {f: _find_value(table_data, pats) for f, pats in _FIELD_MAP.items()}

    # Bid value fallback — largest ₹ amount in text (excluding tender ref numbers)
    if result["Bid_Value"] == "N/A":
        clean = re.sub(r"GEM/\d{4}/[A-Z]/\d+", "", full_text)
        prefixed = re.findall(r"(?:₹|Rs\.?)\s*([0-9][0-9,\.]+)", clean)
        parsed = []
        for a in prefixed:
            try:
                v = int(a.replace(",", "").split(".")[0])
                if v >= 10000:
                    parsed.append(v)
            except ValueError:
                pass
        if parsed:
            result["Bid_Value"] = str(max(parsed))

    # EMD fallback
    if result["EMD"] == "N/A":
        m = re.search(
            r"(?:emd|earnest\s+money)[\s:]*(?:₹|Rs\.?|INR)?\s*([0-9][0-9,\.]+)",
            full_text, re.IGNORECASE,
        )
        if m:
            result["EMD"] = _clean_amount(m.group(1))

    # Delivery fallback
    if result["Delivery"] == "N/A":
        m = re.search(
            r"delivery\s+period\s*(?:\(in\s+days?\))?\s*[\r\n\s:]*(\d+)",
            full_text, re.IGNORECASE | re.DOTALL,
        )
        if m:
            d = int(m.group(1))
            if 1 <= d <= 3650:
                result["Delivery"] = f"{d} Days"

    # Email fallback
    if result["Email"] == "N/A":
        m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_text)
        result["Email"] = m.group() if m else "N/A"

    # Exemption (MSE / Startup)
    mse = re.search(r"mse\s+relaxation\s+for\s+years.*?[:\s]+(yes|no)", full_text, re.IGNORECASE | re.DOTALL)
    startup = re.search(r"startup\s+relaxation\s+for\s+years.*?[:\s]+(yes|no)", full_text, re.IGNORECASE | re.DOTALL)
    exempt_parts = []
    if mse and mse.group(1).lower() == "yes":
        exempt_parts.append("MSE")
    if startup and startup.group(1).lower() == "yes":
        exempt_parts.append("Startup")
    result["Exemption"] = (
        " & ".join(exempt_parts) if exempt_parts
        else ("No" if (mse or startup) else "N/A")
    )

    # Pincode — validate and re-scan if needed
    known_amounts: set[str] = set()
    for af in ("Bid_Value", "EMD"):
        v = result.get(af, "N/A")
        if v and v != "N/A":
            try:
                known_amounts.add(str(int(float(v))))
            except (ValueError, TypeError):
                pass

    raw_pin = result.get("Pincode", "N/A")
    if raw_pin == "N/A" or not _is_valid_pincode(str(raw_pin).strip()) or raw_pin in known_amounts:
        pin_text = re.sub(r"GEM/\d{4}/[A-Z]/\d+", "", full_text)
        result["Pincode"] = "N/A"
        for c in re.findall(r"\b([1-9][0-9]{5})\b", pin_text):
            if _is_valid_pincode(c) and c not in known_amounts:
                result["Pincode"] = c
                break

    # State fallback
    if result["State"] == "N/A":
        lower_text = full_text.lower()
        for state in _INDIAN_STATES:
            if state.lower() in lower_text:
                result["State"] = state
                break

    # Buyer fallback from card dept string
    if result["Buyer"] == "N/A" and dept_addr and dept_addr != "N/A":
        parts = [p.strip() for p in dept_addr.split("|") if p.strip()]
        if len(parts) >= 2:
            result["Buyer"] = parts[-1]

    # Cleaned BOQ — extract from table data
    boq_keys = ("item name", "item description", "description of goods", "product name", "description", "boq")
    boq_lines = []
    for k, v in table_data.items():
        if any(bk in k.lower() for bk in boq_keys):
            val = str(v).strip()
            if len(val) > 3 and val.lower() not in {"n/a", "na", "-"}:
                for part in val.split("|"):
                    part = part.strip()
                    if part and not re.search(r"[\u0900-\u097F]", part):
                        boq_lines.append(part)
    result["Cleaned_BOQ"] = (
        "\n".join(boq_lines[:20]) if boq_lines
        else (items_from_card if items_from_card not in ("N/A", "") else "N/A")
    )

    return result


# ── IT relevance ──────────────────────────────────────────────────────────────

_NON_IT = frozenset([
    "fire extinguisher", "refrigerator", "furniture", "vehicle", "diesel",
    "generator set", "uniform", "stationery", "civil work", "medicine",
    "ambulance", "catering", "food", "clothing", "agriculture",
])
_IT_KW = frozenset([
    "server", "laptop", "desktop", "workstation", "amc", "camc", "fms",
    "networking", "firewall", "hpc", "software", "cloud", "data center",
    "storage", "router", "switch", "it support", "cyber", "cctv",
    "computer", "printer", "scanner", "ups", "wifi", "it services",
    "erp", "crm", "database", "hardware", "bandwidth", "datacenter",
])


def is_it_relevant(items: str, category: str, keyword: str) -> bool:
    combined = f"{items} {category} {keyword}".lower()
    if any(n in combined for n in _NON_IT):
        return False
    return any(k in combined for k in _IT_KW) or True
