"""Job service — CRUD + dispatch.

Uses tenant_id (Clerk user/org ID string) for all ownership checks.
The legacy integer user_id FK is kept in the DB but not used for filtering.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from celery_producer import celery_app
from db_models import Job
from schemas.job import JobCreate


async def create_job(
    db: AsyncSession,
    tenant_id: str,
    data: JobCreate,
) -> Job:
    job = Job(
        user_id=None,       # legacy FK dropped — ownership tracked via tenant_id
        tenant_id=tenant_id,
        keywords=data.keywords,
        cards_per_kw=data.cards_per_kw,
        min_value=data.min_value,
        sort_preference=data.sort_preference,
        status="pending",
        total_keywords=len(data.keywords),
        done_keywords=0,
        total_tenders=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def list_jobs(
    db: AsyncSession,
    tenant_id: str,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
) -> tuple[list[Job], int]:
    q = select(Job).where(Job.tenant_id == tenant_id)
    if status:
        q = q.where(Job.status == status)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Job.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()
    return list(rows), total


async def get_job(db: AsyncSession, tenant_id: str, job_id: int) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def delete_job(db: AsyncSession, tenant_id: str, job_id: int) -> None:
    job = await get_job(db, tenant_id, job_id)
    await db.delete(job)
    await db.commit()


async def dispatch_job(db: AsyncSession, job_id: int) -> str:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    task = celery_app.send_task(
        "tasks.scrape_job.run_scrape_job",
        args=[job_id],
    )
    job.status = "queued"
    job.celery_task_id = task.id
    await db.commit()
    await db.refresh(job)
    return task.id
