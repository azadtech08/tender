"""Billing service — plan and usage tracking (PhonePe gateway handles payments).

Responsibilities:
  - Return or create the current subscription plan for a tenant.
  - Record metered usage events (run / tender / ai_summary).

Payment initiation and webhook handling live in:
  routers/phonepe.py  +  services/phonepe_service.py
"""

from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Subscription, UsageEvent, EVENT_RUN, EVENT_TENDER, EVENT_AI_SUMMARY

logger = structlog.get_logger(__name__)


async def record_usage(
    db: AsyncSession,
    tenant_id: str,
    event_type: str,
    quantity: int = 1,
    job_id: Optional[int] = None,
) -> None:
    """Write a UsageEvent row for metered billing tracking."""
    if event_type not in {EVENT_RUN, EVENT_TENDER, EVENT_AI_SUMMARY}:
        raise ValueError(f"Unknown event_type: {event_type}")

    db.add(UsageEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        quantity=quantity,
        job_id=job_id,
    ))
    await db.flush()
    logger.info("usage.recorded", tenant_id=tenant_id, event_type=event_type, qty=quantity)


async def _get_subscription(db: AsyncSession, tenant_id: str) -> Optional[Subscription]:
    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_current_plan(db: AsyncSession, tenant_id: str) -> Subscription:
    """Return the subscription for this tenant, creating a free one if absent."""
    sub = await _get_subscription(db, tenant_id)
    if sub is None:
        sub = Subscription(tenant_id=tenant_id, plan="free", status="active")
        db.add(sub)
        await db.flush()
    return sub
