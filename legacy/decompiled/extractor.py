import re

# ============================================================================
# FIELD PATTERNS
# ============================================================================
FIELD_MAP = {
    "Ministry": [
        "ministry/state name", "ministry name", "ministry/department", "ministry"
    ],
    "Buyer": [
        "organisation name", "organization name",
        "buyer organisation name", "buyer organization name",
        "buyer name", "buyer organisation", "buyer organization",
        "consignee name", "purchaser name", "office name", "consignee", "buyer"
    ],
    "Bid_Value": [
        "estimated bid value", "estimated value in inr", "estimated value",
        "bid value", "total estimated value", "contract value",
        "bid amount", "tender value", "total value"
    ],
    "EMD": [
        "emd amount", "earnest money deposit", "bid security amount",
        "emd", "earnest money", "bid security"
    ],
    "Delivery": [
        "delivery period in days", "delivery period (in days)",
        "contract period", "delivery period", "supply period",
        "completion period", "delivery timeline", "delivery days",
        "service period", "period of delivery", "period of supply"
    ],
    "Category": [
        "item category", "product category", "primary product category",
        "category name", "item type", "category"
    ],
    "Exemption": [
        "mse relaxation for years of experience and turnover",
        "startup relaxation for years of experience and turnover",
        "mse exemption", "startup exemption", "exemption from emd",
        "emd exemption", "exemption for mse", "exemption for startup",
        "bid security exemption", "emd waiver", "exemption"
    ],
    "Email": [
        "email id", "email address", "contact email",
        "buyer email", "e-mail", "email"
    ],
    "Pincode": [
        "pin code", "pincode", "postal code", "zip code", "pin"
    ],
    "State": [
        "ministry/state name", "state name", "state of delivery",
        "delivery state", "consignee state", "state"
    ],
    "District": [
        "district", "city", "delivery city", "consignee city",
        "delivery district", "district/city"
    ],
    "Product_Type": [
        "type of bid", "bid type", "product type", "type of product",
        "service type", "procurement type", "type"
    ],
}

# ============================================================================
# PINCODE VALIDATION — state-prefix map
# Valid first 2 digits per Indian postal zone
# ============================================================================
VALID_PINCODE_PREFIXES = {
    "11",                          # Delhi
    "12", "13",                    # Haryana
    "14", "15", "16",              # Punjab, Chandigarh
    "17",                          # Himachal Pradesh
    "18", "19",                    # Jammu & Kashmir, Ladakh
    "20", "21", "22", "23", "24", "25", "26", "27", "28",  # Uttar Pradesh
    "30", "31", "32", "33", "34",  # Rajasthan
    "36", "37", "38",              # Gujarat
    "40", "41", "42", "43", "44", "45",  # Maharashtra
    "46", "47", "48", "49",        # Madhya Pradesh, Chhattisgarh
    "50", "51", "52", "53",        # Telangana, Andhra Pradesh
    "56", "57", "58",              # Karnataka
    "60", "61", "62", "63", "64",  # Tamil Nadu
    "67", "68", "69",              # Kerala
    "70", "71", "72", "73", "74",  # West Bengal
    "75", "76", "77",              # Odisha
    "78",                          # Assam, NE states
    "79",                          # Arunachal, Meghalaya, Mizoram, Nagaland, etc.
    "80", "81", "82", "83", "84", "85",  # Bihar, Jharkhand
    "82", "83",                    # Jharkhand
    "110", "111",                  # Delhi (extended)
}

VALID_2_DIGIT_PREFIXES = {
    "11","12","13","14","15","16","17","18","19",
    "20","21","22","23","24","25","26","27","28","29",
    "30","31","32","33","34","36","37","38","39",
    "40","41","42","43","44","45","46","47","48","49",
    "50","51","52","53","54","56","57","58","59",
    "60","61","62","63","64","65","67","68","69",
    "70","71","72","73","74","75","76","77","78","79",
    "80","81","82","83","84","85","86",
}

def _is_valid_pincode(val: str) -> bool:
    """
    Validate Indian pincode:
    - Exactly 6 digits
    - Starts with a valid 2-digit zone prefix
    - Not in common EMD/value range (avoids amounts like 124000, 150000)
    """
    s = str(val).strip()
    if not re.fullmatch(r'\d{6}', s):
        return False
    prefix2 = s[:2]
    if prefix2 not in VALID_2_DIGIT_PREFIXES:
        return False
    # Additional sanity: 3rd digit should be 0-9 but first digit never 0
    if s[0] == '0':
        return False
    return True

# ============================================================================
# NON-IT / IT KEYWORDS
# ============================================================================
NON_IT_KEYWORDS = [
    # Fire / safety equipment
    "fire extinguisher", "fire detection", "fire alarm", "fire fighting",
    "fire suppression", "smoke detector",
    # Mechanical / industrial
    "weapon", "armament", "ammunition", "missile", "gun", "rifle",
    "accelerograph", "seismograph", "flux mapping",
    "refrigerator", "furniture", "vehicle", "tyre",
    "diesel", "generator set", "petrol", "uniform", "stationery",
    "civil work", "construction", "sanitation", "medicine", "drug",
    "ambulance", "water tanker", "catering", "canteen", "food",
    "clothing", "footwear", "agriculture", "fertilizer", "seeds",
    "effluent", "sewage", "lubrication", "lubricant", "welding",
    "hydraulic", "pump", "valve", "pipe fitting", "o ring",
    "electrical fitting", "paint", "cement", "brick", "steel rod",
    "housekeeping", "security guard", "gardening", "cooking",
    "carpeting", "carpet", "curtain", "air conditioner", "hvac",
    "miniature circuit", "circuit breaker",
]

IT_KEYWORDS = [
    "server", "laptop", "desktop", "workstation", "amc", "camc", "cmc",
    "fms", "manpower", "networking", "network", "firewall", "hpc",
    "software", "web portal", "cloud", "ai", "data center", "datacenter",
    "storage", "router", "switch", "it support", "cyber", "surveillance",
    "cctv", "erp", "database", "it infrastructure", "computer",
    "printer", "scanner", "ups", "wifi", "wireless", "it services",
    "annual maintenance", "it hardware", "peripheral", "projector",
    "tablet", "it amc", "it cmc", "it fms"
]

# ============================================================================
# BUYER VALIDATION
# ============================================================================
_HINDI_RE = re.compile(r'[\u0900-\u097F]')
_BUYER_JUNK = re.compile(
    r'[^\x00-\x7F]*/\s*address|address\s*$|^address$|'
    r'bis\s+certificate|is\s+\d{5}|under\s+c[rs]s|'  # spec strings
    r'^yes[,\s]*no$|^no[,\s]*yes$',                   # yes/no combos
    re.IGNORECASE
)
_BUYER_JUNK_WORDS = {
    "yes", "no", "download", "n/a", "na", "-", "none", "null",
    "address", "buyer", "consignee", "name", "not applicable"
}

def _is_valid_buyer(val: str) -> bool:
    if not val or len(val) < 4:
        return False
    # Reject long spec/ATC strings
    if len(val) > 100:
        return False
    if _HINDI_RE.search(val):
        return False
    if _BUYER_JUNK.search(val):
        return False
    if re.fullmatch(r'[\d\s,\.₹]+', val):
        return False
    if val.strip().lower() in _BUYER_JUNK_WORDS:
        return False
    # Reject date strings
    if re.search(r'start\s*date|end\s*date|\d{2}-\d{2}-\d{4}', val, re.IGNORECASE):
        return False
    return True

# ============================================================================
# BUYER FROM DEPARTMENT STRING  (e.g. "Ministry of Defence | Indian Army")
# ============================================================================
def extract_buyer_from_dept(dept: str) -> str:
    """
    Parse buyer from card Department string.
    Format: "Ministry of Defence | Indian Army"
    Rejects: dates, spec text, pure ministry labels
    """
    if not dept or dept == "N/A":
        return "N/A"
    parts = [p.strip() for p in dept.split("|") if p.strip()]
    if len(parts) >= 2:
        buyer = parts[-1]
        # Reject if it's a date string like "Start Date: 28-03-2026 5:00 PM"
        if re.search(r'start\s*date|end\s*date|\d{2}-\d{2}-\d{4}', buyer, re.IGNORECASE):
            return "N/A"
        # Reject if too long (spec text, not org name)
        if len(buyer) > 80:
            return "N/A"
        # Reject obvious junk
        if buyer.lower() in _BUYER_JUNK_WORDS:
            return "N/A"
        return buyer
    return "N/A"

# ============================================================================
# HELPERS
# ============================================================================

def extract_currency(text: str, bid_no: str = "") -> str:
    """Extract estimated bid value, avoiding GEM bid number digit pollution."""
    clean = re.sub(r'GEM/\d{4}/[A-Z]/\d+', '', text)
    if bid_no:
        m = re.search(r'GEM/\d{4}/[A-Z]/(\d+)', bid_no)
        if m:
            clean = clean.replace(m.group(1), '')

    # Strategy 1: labelled value
    labelled = re.findall(
        r'(?:estimated\s+(?:bid\s+)?value|bid\s+value|total\s+(?:bid\s+)?value)'
        r'[\s:]*(?:₹|Rs\.?|INR)?\s*([0-9][0-9,\.]+)',
        clean, re.IGNORECASE
    )
    for raw in labelled:
        val = _clean_amount(raw)
        if val != "N/A":
            try:
                if int(val) >= 10000:
                    return val
            except ValueError:
                pass

    # Strategy 2: ₹ / Rs. prefix
    prefixed = re.findall(r'(?:₹|Rs\.?)\s*([0-9][0-9,\.]+)', clean)
    parsed = []
    for a in prefixed:
        try:
            v = int(a.replace(",", "").split(".")[0])
            if v >= 10000:
                parsed.append(v)
        except ValueError:
            pass
    if parsed:
        return str(max(parsed))

    return "N/A"


def extract_emd(text: str) -> str:
    patterns = [
        r'(?:emd|earnest\s+money(?:\s+deposit)?|bid\s+security(?:\s+amount)?)'
        r'[\s:]*(?:₹|Rs\.?|INR)?\s*([0-9][0-9,\.]+)',
        r'emd\s+amount[\s:₹Rs.INR]*([0-9][0-9,\.]+)',
        r'bid\s+security[\s:₹Rs.INR]*([0-9][0-9,\.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _clean_amount(m.group(1))
            if val != "N/A":
                try:
                    if int(val) >= 100:
                        return val
                except ValueError:
                    return val
    return "N/A"


def extract_delivery(text: str) -> str:
    """
    Extract delivery/supply period. Handles multi-line GeM PDFs where the
    number appears on the line AFTER the label.
    """
    # Multi-line: label on one line, number on next (most common in GeM PDFs)
    multiline_patterns = [
        r'delivery\s+period\s*(?:\(in\s+days?\))?\s*[\r\n\s:]*(\d+)',
        r'supply\s+period\s*[\r\n\s:]*(\d+)',
        r'completion\s+period\s*[\r\n\s:]*(\d+)',
        r'period\s+of\s+(?:delivery|supply)\s*[\r\n\s:]*(\d+)',
    ]
    for pat in multiline_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            days = m.group(1).strip()
            try:
                d = int(days)
                if 1 <= d <= 3650:
                    return f"{d} Days"
            except ValueError:
                pass

    # Inline: "30 days delivery" / "45-day supply period"
    inline = re.findall(r'(\d+)\s*-?\s*days?\s+(?:delivery|supply|from)', text, re.IGNORECASE)
    for d in inline:
        try:
            if 1 <= int(d) <= 3650:
                return f"{d} Days"
        except ValueError:
            pass

    return "N/A"


def extract_email(text: str) -> str:
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    return match.group() if match else "N/A"


def extract_exemption(text: str) -> str:
    """
    Extract MSE / Startup EMD exemption status from PDF text.

    GeM PDFs have TWO types of MSE text:
    1. SPECIFIC field rows (what we want):
       "MSE Relaxation for Years of Experience and Turnover: Yes/No"
       "Startup Relaxation for Years of Experience and Turnover: Yes/No"
       "MSE Exemption: Yes"
    2. BOILERPLATE policy paragraphs (what we must IGNORE):
       "Purchase preference will be given to MSEs as defined in..."
       "MSE category only manufacturers for goods..."

    Strategy: look for the specific labeled fields first.
    Only fall back to general text if specific fields not found.
    """
    # ── Step 1: look for specific labeled YES/NO fields ──────────────────────
    mse_relaxation = re.search(
        r'mse\s+relaxation\s+for\s+years.*?[:\s]+(yes|no)',
        text, re.IGNORECASE | re.DOTALL
    )
    startup_relaxation = re.search(
        r'startup\s+relaxation\s+for\s+years.*?[:\s]+(yes|no)',
        text, re.IGNORECASE | re.DOTALL
    )
    mse_exemption_field = re.search(
        r'(?:mse|msme)\s+exemption\s*[:\s]+(yes|no|applicable|not\s+applicable)',
        text, re.IGNORECASE
    )
    startup_exemption_field = re.search(
        r'startup\s+exemption\s*[:\s]+(yes|no|applicable|not\s+applicable)',
        text, re.IGNORECASE
    )

    # If we found specific fields, use them
    if any([mse_relaxation, startup_relaxation, mse_exemption_field, startup_exemption_field]):
        found = []
        mse_val = None
        startup_val = None

        if mse_relaxation:
            mse_val = mse_relaxation.group(1).lower()
        elif mse_exemption_field:
            mse_val = mse_exemption_field.group(1).lower()

        if startup_relaxation:
            startup_val = startup_relaxation.group(1).lower()
        elif startup_exemption_field:
            startup_val = startup_exemption_field.group(1).lower()

        if mse_val in ("yes", "applicable"):
            found.append("MSE")
        if startup_val in ("yes", "applicable"):
            found.append("Startup")

        if found:
            return " & ".join(found)
        # Both explicitly No
        if mse_val in ("no", "not applicable") or startup_val in ("no", "not applicable"):
            return "No"

    # ── Step 2: fallback — explicit EMD exemption statement (not boilerplate) ─
    # Look for short targeted sentences, not inside long policy paragraphs
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if len(line) > 200:   # skip long boilerplate paragraphs
            continue
        if re.search(r'emd\s+exempt|bid\s+security\s+exempt|earnest\s+money.*exempt',
                     line, re.IGNORECASE):
            if re.search(r'\byes\b|\bapplicable\b', line, re.IGNORECASE):
                return "Applicable"
            if re.search(r'\bno\b|\bnot\b', line, re.IGNORECASE):
                return "No"

    return "N/A"


def extract_boq(table_data: dict, full_text: str, items_from_card: str = "") -> str:
    """
    Extract Cleaned BOQ — a newline-separated list of item names.
    Strips Hindi/Devanagari junk lines and 'View File' artifacts.
    """
    boq_lines = []

    BOQ_KEYS = ["item name", "item description", "description of goods",
                "product name", "name of item", "goods/services",
                "description", "particulars", "boq", "bill of quantity",
                "scope of work", "work description"]

    def _is_clean_boq_line(line: str) -> bool:
        """Return True if line is a valid BOQ item (not junk/Hindi/noise)."""
        if not line or len(line.strip()) < 4:
            return False
        # Reject lines with Hindi/Devanagari characters
        if re.search(r'[\u0900-\u097F]', line):
            return False
        # Reject "View File" artifacts from GeM PDF links
        if re.search(r'view\s*file|click\s*here|download', line, re.IGNORECASE):
            return False
        # Reject pure number/symbol lines
        if re.fullmatch(r'[\d\s,\.₹\-\(\)]+', line):
            return False
        # Reject GST/tax lines
        if re.search(r'gst|applicable\s*i\.?r\.?o|रव|as\s+per\s+(?:gst|tax)',
                     line, re.IGNORECASE):
            return False
        return True

    # Strategy 1: table data
    for k, v in table_data.items():
        k_lower = k.strip().lower()
        if any(bk in k_lower for bk in BOQ_KEYS):
            val = str(v).strip()
            if len(val) > 3 and val.lower() not in {"n/a", "na", "-", ""}:
                parts = [p.strip() for p in val.split("|") if p.strip()]
                for p in parts:
                    if _is_clean_boq_line(p):
                        boq_lines.append(p)

    # Strategy 2: numbered items from full text
    numbered = re.findall(
        r'(?:^|\n)\s*\d+[\.\)]\s*([A-Za-z][^\n]{5,80})',
        full_text
    )
    for item in numbered:
        item = item.strip()
        if re.search(r'page|total|amount|value|quantity|please|note|terms|condition',
                     item, re.IGNORECASE):
            continue
        if _is_clean_boq_line(item):
            boq_lines.append(item)

    # Strategy 3: card Items fallback
    if not boq_lines and items_from_card and items_from_card != "N/A":
        parts = [p.strip() for p in items_from_card.split(",") if p.strip()]
        for p in parts:
            if _is_clean_boq_line(p):
                boq_lines.append(p)

    if not boq_lines:
        return "N/A"

    # Deduplicate, limit to 20 items
    seen = set()
    unique = []
    for line in boq_lines:
        key = line.lower().strip()
        if key not in seen and len(key) > 3:
            seen.add(key)
            unique.append(line)
        if len(unique) >= 20:
            break

    return "\n".join(unique)


def extract_pincode(text: str, exclude_amounts: set = None) -> str:
    """Extract valid Indian pincode, skipping known EMD/value amounts."""
    clean = re.sub(r'GEM/\d{4}/[A-Z]/\d+', '', text)
    candidates = re.findall(r'\b([1-9][0-9]{5})\b', clean)
    for c in candidates:
        if not _is_valid_pincode(c):
            continue
        if exclude_amounts and c in exclude_amounts:
            continue
        return c
    return "N/A"


def _clean_amount(val: str) -> str:
    val = val.strip().replace(",", "")
    try:
        return str(int(float(val)))
    except ValueError:
        return val


def clean_value(val) -> str:
    if val is None:
        return "N/A"
    val = str(val).strip()
    JUNK = {"n/a", "na", "-", "no", "yes", "download", "", "none", "null"}
    if val.lower() in JUNK or len(val) < 2:
        return "N/A"
    if re.fullmatch(r'[\d\s]+', val):
        return "N/A"
    return val


def is_it_relevant(items: str, category: str, keyword: str) -> bool:
    combined = f"{items} {category} {keyword}".lower()
    for nit in NON_IT_KEYWORDS:
        if nit in combined:
            return False
    for it in IT_KEYWORDS:
        if it in combined:
            return True
    return True

# ============================================================================
# TABLE LOOKUP
# ============================================================================

def find_value(data: dict, patterns: list, field: str = "") -> str:
    JUNK = {"yes", "no", "download", "n/a", "na", "-", "none", "null", ""}

    for pattern in patterns:
        for k, v in data.items():
            if k.strip().lower() == pattern.lower():
                val = str(v).strip()
                if val.lower() not in JUNK and len(val) > 1:
                    if field == "Buyer" and not _is_valid_buyer(val):
                        continue
                    return val

    for pattern in patterns:
        for k, v in data.items():
            if pattern.lower() in k.strip().lower():
                val = str(v).strip()
                if val.lower() not in JUNK and len(val) > 1:
                    if field == "Buyer" and not _is_valid_buyer(val):
                        continue
                    return val

    return "N/A"

# ============================================================================
# MAIN EXTRACTION
# ============================================================================

def extract_fields(table_data: dict, full_text: str, bid_no: str = "",
                   dept_addr: str = "", items_from_card: str = "") -> dict:
    result = {}

    # 1. Table extraction
    for field, patterns in FIELD_MAP.items():
        result[field] = clean_value(find_value(table_data, patterns, field))

    # Post-validate Buyer from table
    if result.get("Buyer") != "N/A" and not _is_valid_buyer(result["Buyer"]):
        result["Buyer"] = "N/A"

    # 2. Buyer — fall back to parsing Department string from card
    if result["Buyer"] == "N/A" and dept_addr:
        result["Buyer"] = extract_buyer_from_dept(dept_addr)

    # 3. Text fallbacks
    if result["Bid_Value"] == "N/A":
        result["Bid_Value"] = extract_currency(full_text, bid_no)

    if result["EMD"] == "N/A":
        result["EMD"] = extract_emd(full_text)

    if result["Delivery"] == "N/A":
        result["Delivery"] = extract_delivery(full_text)

    if result["Email"] == "N/A":
        result["Email"] = extract_email(full_text)

    # Exemption — always use dedicated text extractor (table values are unreliable
    # because GeM PDFs have boilerplate MSE text that looks like exemption data)
    result["Exemption"] = extract_exemption(full_text)

    # Pincode — validate strictly, cross-check against known amounts
    known_amounts = set()
    for amt_field in ["Bid_Value", "EMD"]:
        v = result.get(amt_field, "N/A")
        if v and v != "N/A":
            try:
                known_amounts.add(str(int(float(v))))
            except (ValueError, TypeError):
                pass

    raw_pin = result.get("Pincode", "N/A")
    pin_valid = (raw_pin != "N/A"
                 and _is_valid_pincode(str(raw_pin).strip())
                 and str(int(float(raw_pin))) not in known_amounts)

    if not pin_valid:
        result["Pincode"] = extract_pincode(full_text, exclude_amounts=known_amounts)
    else:
        result["Pincode"] = str(int(float(raw_pin)))

    # State fallback
    if result["State"] == "N/A":
        STATES = [
            "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
            "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
            "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
            "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
            "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
            "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi",
            "Jammu & Kashmir", "Ladakh", "Chandigarh", "Puducherry"
        ]
        for state in STATES:
            if state.lower() in full_text.lower():
                result["State"] = state
                break

    # BOQ extraction
    result["Cleaned_BOQ"] = extract_boq(table_data, full_text, items_from_card)

    # 4. Final clean
    for k, v in result.items():
        if isinstance(v, str):
            v = re.sub(r'\s+', ' ', v).strip()
            result[k] = v if v else "N/A"

    return result