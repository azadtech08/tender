"""Tenders router — list and search scraped tenders."""

import os
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import and_, func, nulls_last, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db, get_db_rls
from db_models import COUNTER_TENDERS_EXPORTED, Job, Tender
from schemas.tender import TenderListResponse, TenderResponse
from services.license_enforcement import LicenseGuard, require_valid_license
from services.license_features import (
    FEATURE_EXPORT_XLSX,
    LIMIT_TENDERS_EXPORTED_PER_MONTH,
)
from services.tender_export_service import generate_tender_xlsx
from utils.s3 import download_file

router = APIRouter()

_PDF_DIR = os.environ.get("PDF_DIR", "/pdfs")


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


_DEFAULT_SORT = "bid_start_latest"

_SORT_OPTIONS = {
    "newest":             Tender.id.desc(),
    "bid_start_latest":   nulls_last(Tender.published_date.desc()),
    "bid_start_oldest":   nulls_last(Tender.published_date.asc()),
    "bid_end_latest":     nulls_last(Tender.bid_end_date.desc()),
    "bid_end_oldest":     nulls_last(Tender.bid_end_date.asc()),
}

# Max distinct keywords we combine in a single search (guard against pathological input).
_MAX_SEARCH_KEYWORDS = 25


def _parse_search_keywords(raw: str) -> list[str]:
    """Split free-form search input into keyword phrases.

    Prefers commas as separators so multi-word phrases ("data entry") are
    preserved; falls back to whitespace when no comma is present.
    Deduplicates case-insensitively and caps the list length.
    """
    if not raw or not raw.strip():
        return []
    parts = raw.split(",") if "," in raw else raw.split()
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        kw = p.strip()
        if not kw:
            continue
        key = kw.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(kw)
        if len(out) >= _MAX_SEARCH_KEYWORDS:
            break
    return out


def _build_tsquery(keywords: list[str], match: str):
    """Combine per-keyword plainto_tsqueries with OR (||) or AND (&&)."""
    parts = [func.plainto_tsquery(text("'english'"), kw) for kw in keywords]
    combined = parts[0]
    op = "&&" if match == "all" else "||"
    for p in parts[1:]:
        combined = combined.op(op)(p)
    return combined


@router.get("/ministries")
async def list_ministries(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_rls)],
) -> list[str]:
    """Return distinct ministry values for the current tenant."""
    result = await db.execute(
        select(Tender.ministry)
        .where(Tender.tenant_id == current_user.tenant_id, Tender.ministry.isnot(None))
        .distinct()
        .order_by(Tender.ministry)
    )
    return [row for (row,) in result.all()]


@router.get("", response_model=TenderListResponse)
async def list_tenders(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_rls)],
    guard: Annotated[LicenseGuard, Depends(require_valid_license)],  # noqa: ARG001
    job_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    search: str | None = Query(default=None),
    match: str = Query(default="any", pattern="^(any|all)$"),
    ministry: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> TenderListResponse:
    # Base query — scoped to current tenant via tenant_id (RLS also enforces this)
    q = (
        select(Tender)
        .where(Tender.tenant_id == current_user.tenant_id)
    )

    if job_id is not None:
        q = q.where(Tender.job_id == job_id)

    if keyword:
        q = q.where(Tender.keyword.ilike(f"%{keyword}%"))

    if ministry:
        ministry_list = [m.strip() for m in ministry.split(",") if m.strip()]
        if len(ministry_list) == 1:
            q = q.where(Tender.ministry == ministry_list[0])
        else:
            q = q.where(Tender.ministry.in_(ministry_list))

    # Parse possibly multi-keyword search (comma- or whitespace-separated).
    # `match=any` → OR semantics (default, GeM-like), `match=all` → AND semantics.
    search_keywords = _parse_search_keywords(search) if search else []
    combined_tsq = None
    if search_keywords:
        try:
            combined_tsq = _build_tsquery(search_keywords, match)
            q = q.where(Tender.search_vector.op("@@")(combined_tsq))
        except AttributeError:
            # Older schema without search_vector — degrade to ILIKE.
            clauses = []
            for kw in search_keywords:
                pat = f"%{kw}%"
                clauses.append(
                    or_(
                        Tender.title.ilike(pat),
                        Tender.description.ilike(pat),
                        Tender.organisation.ilike(pat),
                    )
                )
            q = q.where(or_(*clauses) if match == "any" else and_(*clauses))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Ordering — explicit sort param > FTS rank > default (bid_start_latest)
    effective_sort = sort if (sort and sort in _SORT_OPTIONS) else None
    if effective_sort:
        q = q.order_by(_SORT_OPTIONS[effective_sort], Tender.id.desc())
    elif combined_tsq is not None:
        try:
            rank = func.ts_rank(Tender.search_vector, combined_tsq)
            q = q.order_by(rank.desc(), Tender.id.desc())
        except AttributeError:
            q = q.order_by(_SORT_OPTIONS[_DEFAULT_SORT], Tender.id.desc())
    else:
        q = q.order_by(_SORT_OPTIONS[_DEFAULT_SORT], Tender.id.desc())

    q = q.offset((page - 1) * per_page).limit(per_page)
    tenders = (await db.execute(q)).scalars().all()

    return TenderListResponse(
        items=[TenderResponse.model_validate(t) for t in tenders],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/export/xlsx")
async def export_tenders_xlsx(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_rls)],
    guard: Annotated[LicenseGuard, Depends(require_valid_license)],
    search: str | None = Query(default=None),
) -> Response:
    """Export all tenders as Excel file (.xlsx).

    Generates a deduplicated, formatted Excel file with all tenders for the current user.
    File includes proper formatting: bold headers, filters, frozen top row, and auto-fit columns.
    Sorted by Bid End Date ascending.
    """
    guard.require_feature(FEATURE_EXPORT_XLSX)
    try:
        xlsx_bytes = await generate_tender_xlsx(db, current_user.tenant_id, search)
        await guard.check_and_increment(
            db,
            COUNTER_TENDERS_EXPORTED,
            max_key=LIMIT_TENDERS_EXPORTED_PER_MONTH,
        )
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"GeM_Tenders_{timestamp}.xlsx"

        _CONTENT_TYPE = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        return Response(
            content=xlsx_bytes,
            media_type=_CONTENT_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate export: {str(exc)}",
        )


@router.delete("/{tender_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tender(
    tender_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_rls)],
):
    """Delete a single tender. Tenant-scoped — users can only delete their own."""
    result = await db.execute(
        select(Tender).where(
            Tender.id == tender_id,
            Tender.tenant_id == current_user.tenant_id,
        )
    )
    tender = result.scalar_one_or_none()
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    await db.delete(tender)
    await db.commit()
    return None


@router.get("/{tender_id}/pdf")
async def download_tender_pdf(
    tender_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_rls)],
):
    """Download the source PDF for a tender.

    Tries the shared local volume first (worker writes PDFs to /pdfs),
    then falls back to S3/R2 when `pdf_s3_key` is set.
    """
    result = await db.execute(
        select(Tender).where(
            Tender.id == tender_id,
            Tender.tenant_id == current_user.tenant_id,
        )
    )
    tender = result.scalar_one_or_none()
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    filename = f"{_safe_filename(tender.tender_ref_no)}.pdf"
    local_path = os.path.join(_PDF_DIR, filename)

    if os.path.isfile(local_path):
        return FileResponse(
            local_path,
            media_type="application/pdf",
            filename=filename,
        )

    # Fallback: S3/R2
    if tender.pdf_s3_key:
        data = download_file(tender.pdf_s3_key)
        if data:
            from fastapi.responses import Response
            return Response(
                content=data,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="PDF not available for this tender",
    )
