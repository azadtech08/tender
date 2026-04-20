import re

def clean_text(text) -> str:
    """
    Remove CID junk, normalize whitespace, and strip Hindi characters.
    Also removes leading/trailing slashes often found in GeM headers.
    """
    if not text:
        return ""
    
    # 1. Convert to string and remove Devanagari (Hindi) characters
    text = str(text)
    text = re.sub(r'[\u0900-\u097F]', '', text)
    
    # 2. Remove CID junk (e.g., (cid:123))
    text = re.sub(r'\(cid:\d+\)', '', text)
    
    # 3. Remove leading/trailing slashes and excess whitespace
    text = re.sub(r'^\s*/\s*|\s*/\s*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def safe_filename(name: str) -> str:
    """Make a string safe to use as a filename."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def find_value(data: dict, patterns: list) -> str:
    """
    Search table_data dict for the best matching value.
    Tries exact match first, then partial.
    Skips junk values like 'Yes', 'No', 'Download'.
    """
    junk = {"yes", "no", "download", "n/a", "na", "-", "none", "null", ""}

    for pattern in patterns:
        # Exact key match
        for k, v in data.items():
            if k.strip().lower() == pattern.lower():
                val = str(v).strip()
                if val.lower() not in junk:
                    return val

    for pattern in patterns:
        # Partial key match
        for k, v in data.items():
            if pattern.lower() in k.strip().lower():
                val = str(v).strip()
                if val.lower() not in junk and len(val) > 1:
                    return val

    return "N/A"