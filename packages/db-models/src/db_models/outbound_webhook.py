"""Outbound webhook model — tenant-defined HTTP callbacks."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class OutboundWebhook(Base, TimestampMixin):
    """Webhook endpoint registered by a tenant.

    Supported events (stored as JSONB list):
      job.completed, job.failed, tender.new

    Delivery uses HMAC-SHA256 with ``secret`` in the ``X-Gem-Signature`` header.
    """

    __tablename__ = "outbound_webhooks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        comment='e.g. ["job.completed", "tender.new"]',
    )
    secret: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="HMAC-SHA256 signing secret (shown once at creation)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_outbound_webhooks_tenant", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<OutboundWebhook(id={self.id}, url={self.url!r})>"


class WebhookDelivery(Base):
    """Log of each outbound webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    webhook_id: Mapped[int] = mapped_column(
        ForeignKey("outbound_webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
