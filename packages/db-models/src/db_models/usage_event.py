"""UsageEvent model — per-event metered billing records."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

# Event types — must match CLAUDE.md pricing: ₹15/run, ₹2/tender, ₹3/ai_summary
EVENT_RUN = "run"
EVENT_TENDER = "tender"
EVENT_AI_SUMMARY = "ai_summary"

VALID_EVENT_TYPES = {EVENT_RUN, EVENT_TENDER, EVENT_AI_SUMMARY}


class UsageEvent(Base, TimestampMixin):
    """A single metered billing event for a tenant.

    Written by the API when:
    - A job is dispatched → event_type="run", quantity=1
    - Tenders are ingested → event_type="tender", quantity=N
    - An AI summary is generated → event_type="ai_summary", quantity=1

    A background task (Phase 3) reads unreported rows, batches them,
    and posts usage records to Stripe's metered billing API, then sets
    reported_to_stripe=True.
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Stripe reporting state.
    reported_to_stripe: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    stripe_usage_record_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    reported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional: link back to the job that generated this event.
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    __table_args__ = (
        Index("ix_usage_events_unreported", "tenant_id", "reported_to_stripe"),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageEvent(tenant_id={self.tenant_id}, type={self.event_type}, "
            f"qty={self.quantity}, reported={self.reported_to_stripe})>"
        )
