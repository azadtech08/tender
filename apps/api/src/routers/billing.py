"""Billing API router.

Endpoints:
  GET  /api/billing/plan               — current subscription plan + status
  POST /api/billing/checkout           — create Stripe Checkout Session URL
  POST /api/billing/portal             — create Stripe Customer Portal URL
  GET  /api/billing/usage              — usage events for current billing period
"""

from typing import Annotated, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from config import settings
from database import get_db_rls
from db_models import Subscription, UsageEvent
from services.billing_service import (
    create_checkout_session,
    create_portal_session,
    get_current_plan,
)

router = APIRouter()


# ── Pydantic response models ─────────────────────────────────────────────────

class PlanResponse(BaseModel):
    tenant_id: str
    plan: str
    status: str
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    stripe_customer_id: Optional[str]

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    plan: str         # starter | pro | business
    success_path: str = "/dashboard?upgraded=1"
    cancel_path: str = "/dashboard/billing"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_path: str = "/dashboard/billing"


class PortalResponse(BaseModel):
    portal_url: str


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


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Create a Stripe Checkout Session to upgrade the subscription plan."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe not configured",
        )
    if body.plan not in ("starter", "pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plan must be one of: starter, pro, business",
        )

    base = settings.app_base_url.rstrip("/")
    url = await create_checkout_session(
        db=db,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        plan=body.plan,
        success_url=f"{base}{body.success_path}",
        cancel_url=f"{base}{body.cancel_path}",
    )
    return CheckoutResponse(checkout_url=url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    body: PortalRequest,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Create a Stripe Customer Portal session for subscription management."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe not configured",
        )

    base = settings.app_base_url.rstrip("/")
    url = await create_portal_session(
        db=db,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        return_url=f"{base}{body.return_path}",
    )
    return PortalResponse(portal_url=url)


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
