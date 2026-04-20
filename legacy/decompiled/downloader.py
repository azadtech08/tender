import os
import requests
from utils import safe_filename

BASE_URL = "https://bidplus.gem.gov.in/all-bids"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept": "application/pdf,*/*",
}


def download_pdf(url: str, bid_id: str, save_dir: str) -> str | None:
    """Download a bid PDF with browser-like headers. Returns local path or None."""
    os.makedirs(save_dir, exist_ok=True)
    filename = safe_filename(bid_id) + ".pdf"
    path = os.path.join(save_dir, filename)

    # Skip re-download if file already exists
    if os.path.exists(path):
        return path

    try:
        r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        r.raise_for_status()

        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        return path

    except Exception as e:
        print(f"   [Download Error] {e}")
        return None