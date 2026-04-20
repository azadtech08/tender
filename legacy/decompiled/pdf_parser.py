import pdfplumber
import re
from utils import clean_text

# ============================================================================
# TABLE PARSER
# ============================================================================

def parse_tables(pdf):
    """
    Walk every table on every page, build a flat {label: value} dict.
    GeM PDFs use a two-column layout: label (Hindi+English) | value.
    """
    data = {}
    
    # Specific settings to capture GeM's thin-line table structures
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
    }

    for page in pdf.pages:
        tables = page.extract_tables(table_settings=table_settings)

        for table in tables:
            for row in table:
                if not row:
                    continue

                # Clean each cell in the row
                cells = [clean_text(c) for c in row if c and clean_text(c)]

                if len(cells) < 2:
                    continue

                # Strategy: Use first cell as key, last cell as value
                key = cells[0].lower().strip()
                value = cells[-1].strip()

                # Basic validation for keys
                if (
                    len(key) < 3
                    or len(key) > 100
                    or re.fullmatch(r'[\d\s₹,\.]+', key)
                    or len(value) < 1
                ):
                    continue

                # Store or merge multi-line entries
                if key in data:
                    if value not in data[key]:
                        data[key] += f" | {value}"
                else:
                    data[key] = value

                # Also try all consecutive pairs for complex/nested tables
                for i in range(len(cells) - 1):
                    k = cells[i].lower().strip()
                    v = cells[i + 1].strip()
                    if 3 <= len(k) <= 100 and not re.fullmatch(r'[\d\s₹,\.]+', k):
                        if k not in data:
                            data[k] = v
                        elif v and v not in data[k]:
                            data[k] += f" | {v}"

    return data


# ============================================================================
# TEXT PARSER
# ============================================================================

def parse_text(pdf):
    """Extract plain text from every page and normalize."""
    full_text = ""
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            full_text += clean_text(text) + "\n"
    return full_text.strip()


# ============================================================================
# MAIN ENTRY
# ============================================================================

def parse_pdf(file_path: str):
    """Open the PDF and return (table_data dict, full_text string)."""
    table_data = {}
    full_text  = ""

    try:
        with pdfplumber.open(file_path) as pdf:
            # We parse tables first to get structured data
            table_data = parse_tables(pdf)
            # Then get full text for fallback regex matching
            full_text = parse_text(pdf)
            # Normalize whitespace across the entire text block
            full_text = re.sub(r'\s+', ' ', full_text).strip()

    except Exception as e:
        print(f"   [PDF Error] {e}")

    return table_data, full_text