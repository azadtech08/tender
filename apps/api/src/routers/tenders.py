"""Tenders router — list and search scraped tenders."""

import os
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, nulls_last, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db
from db_models import Job, Tender
from schemas.tender import TenderListResponse, TenderResponse
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


@router.get("/ministries")
async def list_ministries(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    db: Annotated[AsyncSession, Depends(get_db)],
    job_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    search: str | None = Query(default=None),
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

    if search:
        # Use Postgres FTS via search_vector (tsvector + GIN index) when available;
        # fall back to ILIKE if the column doesn't exist yet (pre-migration envs).
        try:
            tsq = func.plainto_tsquery(text("'english'"), search)
            q = q.where(Tender.search_vector.op("@@")(tsq))
        except AttributeError:
            # Older schema without search_vector — degrade gracefully
            pattern = f"%{search}%"
            q = q.where(
                or_(
                    Tender.title.ilike(pattern),
                    Tender.description.ilike(pattern),
                    Tender.organisation.ilike(pattern),
                )
            )

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Ordering — explicit sort param > FTS rank > default (bid_start_latest)
    effective_sort = sort if (sort and sort in _SORT_OPTIONS) else None
    if effective_sort:
        q = q.order_by(_SORT_OPTIONS[effective_sort], Tender.id.desc())
    elif search:
        try:
            tsq = func.plainto_tsquery(text("'english'"), search)
            rank = func.ts_rank(Tender.search_vector, tsq)
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
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None),
) -> Response:
    """Export all tenders as Excel file (.xlsx).

    Generates a deduplicated, formatted Excel file with all tenders for the current user.
    File includes proper formatting: bold headers, filters, frozen top row, and auto-fit columns.
    Sorted by Bid End Date ascending.
    """
    try:
        xlsx_bytes = await generate_tender_xlsx(db, current_user.tenant_id, search)
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
    db: Annotated[AsyncSession, Depends(get_db)],
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
    db: Annotated[AsyncSession, Depends(get_db)],
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
