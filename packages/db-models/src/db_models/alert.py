"""Alert model — saved search rules that trigger email / Slack digests."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Alert(Base, TimestampMixin):
    """A saved alert rule owned by a tenant.

    The worker's digest task evaluates all active alerts daily and emails
    matching tenders to ``email_to`` and/or posts to ``slack_webhook_url``.

    Filter logic (all conditions ANDed):
      - keyword ILIKE any of ``keywords`` (comma-separated, optional)
      - tender_value >= min_value (optional)
      - state == state_filter (optional)
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Filter conditions ────────────────────────────────────────────────────
    keywords: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Comma-separated keywords; NULL means any keyword",
    )
    min_value: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    state_filter: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Delivery channels ────────────────────────────────────────────────────
    email_to: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Comma-separated recipient email addresses",
    )
    slack_webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── State ────────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_alerts_tenant_active", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, name={self.name!r}, tenant={self.tenant_id})>"


class AlertDelivery(Base):
    """Log of each alert delivery attempt (email / Slack)."""

    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)   # email | slack
    status: Mapped[str] = mapped_column(String(20), nullable=False)    # sent | failed
    tenders_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
