"""Jobs router — CRUD + Celery dispatch + SSE event stream + scheduling."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user, verify_token
from database import get_db
from db_models import Job, JobEvent, Schedule
from schemas.job import JobCreate, JobListResponse, JobResponse
from services.job_service import (
    create_job,
    delete_job,
    dispatch_job,
    get_job,
    list_jobs,
)

router = APIRouter()


# ── Schedule schemas ──────────────────────────────────────────────────────────

class ScheduleUpsert(BaseModel):
    cron_hour:   int = Field(default=9,  ge=0, le=23)
    cron_minute: int = Field(default=0,  ge=0, le=59)
    is_active:   bool = True


class ScheduleResponse(BaseModel):
    id:          int
    job_id:      int
    cron_hour:   int
    cron_minute: int
    is_active:   bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]

    model_config = {"from_attributes": True}

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job_endpoint(
    data: JobCreate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    job = await create_job(db, current_user.tenant_id, data)
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs_endpoint(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> JobListResponse:
    jobs, total = await list_jobs(db, current_user.tenant_id, page, per_page, status)
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_endpoint(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    job = await get_job(db, current_user.tenant_id, job_id)
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_endpoint(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await delete_job(db, current_user.tenant_id, job_id)


@router.post("/{job_id}/run", response_model=JobResponse)
async def run_job_endpoint(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    # Verify ownership first
    job = await get_job(db, current_user.tenant_id, job_id)
    if job.status in _TERMINAL_STATUSES or job.status == "running":
        # Re-run: reset counters
        job.status = "pending"
        job.done_keywords = 0
        job.total_tenders = 0
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        await db.commit()

    await dispatch_job(db, job_id)
    job = await get_job(db, current_user.tenant_id, job_id)
    return JobResponse.model_validate(job)


@router.get("/{job_id}/events")
async def job_events_stream(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Query(..., description="Bearer token (EventSource can't send headers)"),
    last_event_id: int = Query(default=0),
) -> StreamingResponse:
    token_data = verify_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Verify job ownership
    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == token_data.tenant_id)
    )
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        cursor = last_event_id
        while True:
            # Fetch new events since last cursor
            events_result = await db.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.id > cursor)
                .order_by(JobEvent.id)
                .limit(50)
            )
            events = events_result.scalars().all()

            for event in events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                yield (
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(payload)}\n"
                    f"id: {event.id}\n\n"
                )
                cursor = event.id

            # Check if job is done
            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job and job.status in _TERMINAL_STATUSES:
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Schedule endpoints ────────────────────────────────────────────────────────

def _next_run(hour: int, minute: int) -> datetime:
    """Calculate the next UTC datetime for the given hour:minute (IST = UTC+5:30)."""
    from datetime import timedelta
    now_ist = datetime.now(tz=timezone.utc) + timedelta(hours=5, minutes=30)
    target  = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_ist:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


@router.patch("/{job_id}/schedule", response_model=ScheduleResponse)
async def upsert_schedule(
    job_id: int,
    body: ScheduleUpsert,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleResponse:
    """Create or update a daily recurring schedule for a job (time in IST)."""
    # Verify job ownership
    await get_job(db, current_user.tenant_id, job_id)

    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()

    next_run = _next_run(body.cron_hour, body.cron_minute) if body.is_active else None

    if schedule:
        schedule.cron_hour   = body.cron_hour
        schedule.cron_minute = body.cron_minute
        schedule.is_active   = body.is_active
        schedule.next_run_at = next_run
    else:
        schedule = Schedule(
            job_id      = job_id,
            cron_hour   = body.cron_hour,
            cron_minute = body.cron_minute,
            is_active   = body.is_active,
            next_run_at = next_run,
        )
        db.add(schedule)

    await db.commit()
    await db.refresh(schedule)
    return ScheduleResponse.model_validate(schedule)


@router.get("/{job_id}/schedule", response_model=ScheduleResponse)
async def get_schedule(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleResponse:
    """Get the schedule for a job, if one exists."""
    await get_job(db, current_user.tenant_id, job_id)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No schedule for this job")
    return ScheduleResponse.model_validate(schedule)


@router.delete("/{job_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    job_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove the recurring schedule for a job."""
    await get_job(db, current_user.tenant_id, job_id)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if schedule:
        await db.delete(schedule)
        await db.commit()
