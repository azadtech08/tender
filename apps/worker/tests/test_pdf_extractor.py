"""PDF extractor regression tests.

Runs against all 30 PDFs in downloads/.  For each file:
  - parse_pdf() must not raise
  - extract_fields() must return a dict with all expected keys
  - At least 95% of the 11 structured fields must be non-N/A across the corpus

Run with (from repo root):
    pytest apps/worker/tests/test_pdf_extractor.py -v

The test adds the worker/src directory to sys.path so it can import the
scraper package without installing it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER_SRC = REPO_ROOT / "apps" / "worker" / "src"
PDF_DIR    = REPO_ROOT / "downloads"

if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from scraper.pdf_extractor import extract_fields, parse_pdf  # noqa: E402

# ── Corpus ────────────────────────────────────────────────────────────────────

def _all_pdfs() -> list[Path]:
    if not PDF_DIR.exists():
        return []
    return sorted(PDF_DIR.glob("*.pdf"))


ALL_PDFS = _all_pdfs()

# Fields we assert on — must be present as keys (value may be N/A for some PDFs)
EXPECTED_KEYS = {
    "Ministry", "Buyer", "Bid_Value", "EMD", "Delivery",
    "Category", "Exemption", "Email", "Pincode", "State",
    "Product_Type", "Cleaned_BOQ",
}

# Fields that count toward the 95% fill-rate metric
SCORED_FIELDS = ["Ministry", "Buyer", "Bid_Value", "State", "Email"]


# ── Individual PDF tests ──────────────────────────────────────────────────────

@pytest.mark.skipif(not ALL_PDFS, reason="No PDFs in downloads/ — run from repo root")
@pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=lambda p: p.name)
def test_parse_does_not_raise(pdf_path: Path) -> None:
    """parse_pdf must complete without exception for every PDF in corpus."""
    table_data, full_text = parse_pdf(str(pdf_path))
    assert isinstance(table_data, dict)
    assert isinstance(full_text, str)


@pytest.mark.skipif(not ALL_PDFS, reason="No PDFs in downloads/")
@pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=lambda p: p.name)
def test_extract_fields_keys_present(pdf_path: Path) -> None:
    """extract_fields must return all expected field keys."""
    table_data, full_text = parse_pdf(str(pdf_path))
    result = extract_fields(table_data, full_text)
    missing = EXPECTED_KEYS - set(result.keys())
    assert not missing, f"{pdf_path.name}: missing keys {missing}"


# ── Corpus-wide fill-rate assertion ──────────────────────────────────────────

@pytest.mark.skipif(not ALL_PDFS, reason="No PDFs in downloads/")
def test_corpus_field_fill_rate() -> None:
    """Across all 30 PDFs, each scored field must be non-N/A for ≥95% of files."""
    total = len(ALL_PDFS)
    assert total == 30, f"Expected 30 PDFs in corpus, found {total}"

    field_hits: dict[str, int] = {f: 0 for f in SCORED_FIELDS}

    for pdf_path in ALL_PDFS:
        table_data, full_text = parse_pdf(str(pdf_path))
        result = extract_fields(table_data, full_text)
        for field in SCORED_FIELDS:
            val = result.get(field, "N/A")
            if val and val != "N/A":
                field_hits[field] += 1

    threshold = 0.95
    failures: list[str] = []
    for field, hits in field_hits.items():
        rate = hits / total
        if rate < threshold:
            failures.append(
                f"  {field}: {hits}/{total} = {rate:.0%} (need ≥{threshold:.0%})"
            )

    assert not failures, (
        f"Field fill-rate below 95% for {len(failures)} field(s):\n"
        + "\n".join(failures)
    )


# ── Sanity: corpus size ───────────────────────────────────────────────────────

def test_corpus_has_30_pdfs() -> None:
    assert len(ALL_PDFS) == 30, (
        f"Expected 30 PDFs in {PDF_DIR}, found {len(ALL_PDFS)}. "
        "Make sure the downloads/ directory is at the repo root."
    )
