"""Billing API router.

Endpoints:
  GET  /api/billing/plan               — current subscription plan + status
  GET  /api/billing/usage              — usage events for current billing period

Payment initiation is handled by /api/billing/phonepe/* (PhonePe gateway).
"""

from typing import Annotated, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db_rls
from db_models import Subscription, UsageEvent
from services.billing_service import get_current_plan

router = APIRouter()


# ── Pydantic response models ─────────────────────────────────────────────────

class PlanResponse(BaseModel):
    tenant_id: str
    plan: str
    status: str
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool

    model_config = {"from_attributes": True}


class UsageSummaryResponse(BaseModel):
    runs: int
    tenders: int
    ai_summaries: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/plan", response_model=PlanResponse)
async def get_plan(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Return the current subscription plan for this tenant."""
    sub = await get_current_plan(db, current_user.tenant_id)
    return sub


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Return aggregated usage counts for this tenant (all time)."""
    result = await db.execute(
        select(
            UsageEvent.event_type,
            func.sum(UsageEvent.quantity).label("total"),
        )
        .where(UsageEvent.tenant_id == current_user.tenant_id)
        .group_by(UsageEvent.event_type)
    )
    rows = result.all()
    totals = {row.event_type: int(row.total) for row in rows}
    return UsageSummaryResponse(
        runs=totals.get("run", 0),
        tenders=totals.get("tender", 0),
        ai_summaries=totals.get("ai_summary", 0),
    )
