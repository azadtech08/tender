"""Exports router — XLSX file download for a job."""

import asyncio
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db
from db_models import COUNTER_TENDERS_EXPORTED
from services.export_service import generate_xlsx
from services.license_enforcement import LicenseGuard, require_valid_license
from services.license_features import (
    FEATURE_EXPORT_XLSX,
    LIMIT_TENDERS_EXPORTED_PER_MONTH,
)
from utils.s3 import generate_presigned_url, upload_file

logger = structlog.get_logger(__name__)

router = APIRouter()

_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/{job_id}.xlsx")
async def download_xlsx(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    guard: Annotated[LicenseGuard, Depends(require_valid_license)],
) -> Response:
    guard.require_feature(FEATURE_EXPORT_XLSX)
    xlsx_bytes = await generate_xlsx(db, job_id, current_user.tenant_id)
    # Count rows after generating so we increment by the actual export size,
    # not the request count. Falls back to 1 on parse failure.
    try:
        import openpyxl  # noqa: PLC0415 — local import keeps cold-start small
        from io import BytesIO  # noqa: PLC0415

        wb = openpyxl.load_workbook(BytesIO(xlsx_bytes), read_only=True)
        ws = wb.active
        # Subtract header row.
        row_count = max(0, (ws.max_row or 1) - 1)
        wb.close()
    except Exception:
        row_count = 1
    await guard.check_and_increment(
        db,
        COUNTER_TENDERS_EXPORTED,
        max_key=LIMIT_TENDERS_EXPORTED_PER_MONTH,
        n=max(1, row_count),
    )
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"Tenders_{job_id}_{timestamp}.xlsx"

    # Upload to S3/R2 in the background (best-effort, never blocks the download)
    s3_key = f"exports/{current_user.tenant_id}/{filename}"
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: upload_file(s3_key, xlsx_bytes, content_type=_CONTENT_TYPE),
        )
    except Exception as exc:
        logger.warning("export.s3_upload_failed", job_id=job_id, error=str(exc))

    return Response(
        content=xlsx_bytes,
        media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
