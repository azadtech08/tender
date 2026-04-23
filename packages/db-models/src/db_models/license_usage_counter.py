"""License usage counter — per-license daily/monthly tallies.

Atomic upsert pattern for concurrent-safe increments:

    INSERT INTO license_usage_counters (license_id, period_start, counter_name,
                                         tenant_id, count)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (license_id, period_start, counter_name)
    DO UPDATE SET count = license_usage_counters.count + EXCLUDED.count,
                  updated_at = now();
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Standard counter names — use these constants so admin UI and enforcement
# code agree on keys. Additional counter names are allowed (free-form).
COUNTER_RUNS = "runs"
COUNTER_TENDERS_EXPORTED = "tenders_exported"
COUNTER_AI_SUMMARIES = "ai_summaries"
COUNTER_API_CALLS = "api_calls"


class LicenseUsageCounter(Base):
    """Composite-key tally row. No surrogate id."""

    __tablename__ = "license_usage_counters"

    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)
    counter_name: Mapped[str] = mapped_column(String(64), primary_key=True)

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    license: Mapped["License"] = relationship(  # noqa: F821
        "License", back_populates="usage_counters"
    )

    __table_args__ = (
        Index(
            "ix_license_usage_tenant_period",
            "tenant_id",
            "period_start",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseUsageCounter(license_id={self.license_id}, "
            f"period={self.period_start}, {self.counter_name}={self.count})>"
        )
