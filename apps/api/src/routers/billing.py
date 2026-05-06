"""Billing API router.

Endpoints:
  GET  /api/billing/plan               — current subscription plan + status
  GET  /api/billing/usage              — usage events for current billing period

Payment initiation is handled by /api/billing/phonepe/* (PhonePe gateway).
"""

from typing import Annotated, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db, get_db_rls
from db_models import STATUS_ACTIVE, License, Subscription, UsageEvent
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


class AccessStatusResponse(BaseModel):
    has_access: bool
    reason: str          # "subscribed" | "trial_active" | "trial_expired" | "no_access"
    days_remaining: Optional[int]    # set only for trial_active
    expires_at: Optional[datetime]   # trial end or subscription period end
    plan: Optional[str]              # plan name when has_access is True


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


@router.get("/access-status", response_model=AccessStatusResponse)
async def get_access_status(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Return whether this tenant has active access and why.

    Checks subscription (PhonePe) first, then license key (trial).
    Uses get_db (no RLS) so we can check BOTH the user's org_id and user_id —
    Clerk's JWT may omit org_id when the user is in personal context, but the
    license may have been minted for either identity.
    """
    now = datetime.now(tz=timezone.utc)

    # Collect both identities: org_id (if JWT has one) and raw user_id.
    # A license minted for either should grant access.
    tenant_ids = list({current_user.tenant_id, current_user.user_id})

    # ── Path 1: active subscription (PhonePe payment) ────────────────────────
    sub_result = await db.execute(
        select(Subscription).where(Subscription.tenant_id.in_(tenant_ids))
    )
    sub = sub_result.scalar_one_or_none()
    if (
        sub is not None
        and sub.status == "active"
        and sub.current_period_end is not None
        and sub.current_period_end > now
    ):
        return AccessStatusResponse(
            has_access=True,
            reason="subscribed",
            days_remaining=None,
            expires_at=sub.current_period_end,
            plan=sub.plan,
        )

    # ── Path 2: active license key (trial) ───────────────────────────────────
    lic_result = await db.execute(
        select(License)
        .where(
            License.tenant_id.in_(tenant_ids),
            License.status == STATUS_ACTIVE,
        )
        .order_by(License.expires_at.desc())
        .limit(1)
    )
    lic = lic_result.scalar_one_or_none()

    if lic is not None:
        if lic.expires_at > now:
            days_remaining = max(0, (lic.expires_at.date() - now.date()).days)
            return AccessStatusResponse(
                has_access=True,
                reason="trial_active",
                days_remaining=days_remaining,
                expires_at=lic.expires_at,
                plan=lic.plan,
            )
        else:
            return AccessStatusResponse(
                has_access=False,
                reason="trial_expired",
                days_remaining=0,
                expires_at=lic.expires_at,
                plan=lic.plan,
            )

    # ── No license or subscription found ─────────────────────────────────────
    return AccessStatusResponse(
        has_access=False,
        reason="no_access",
        days_remaining=None,
        expires_at=None,
        plan=None,
    )
