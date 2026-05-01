"""Subscription model — tracks plan state per tenant."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

# Valid plan slugs — matches CLAUDE.md pricing table.
PLAN_FREE = "free"
PLAN_STARTER = "starter"
PLAN_PRO = "pro"
PLAN_BUSINESS = "business"
PLAN_ENTERPRISE = "enterprise"

VALID_PLANS = {PLAN_FREE, PLAN_STARTER, PLAN_PRO, PLAN_BUSINESS, PLAN_ENTERPRISE}

# Monthly run limits per plan (None = unlimited).
PLAN_RUN_LIMITS: dict[str, Optional[int]] = {
    PLAN_FREE: 3,
    PLAN_STARTER: 30,
    PLAN_PRO: 150,
    PLAN_BUSINESS: 600,
    PLAN_ENTERPRISE: None,
}


class Subscription(Base, TimestampMixin):
    """Plan subscription state for a tenant.

    One row per tenant. Created automatically when a tenant first registers
    (plan = free). Updated by PhonePe payment webhook events.

    Status values: active, trialing, past_due, cancelled.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PLAN_FREE
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active"
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription(tenant_id={self.tenant_id}, plan={self.plan}, "
            f"status={self.status})>"
        )
