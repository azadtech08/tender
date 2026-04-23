"""License device model — one row per (license, fingerprint) pair."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class LicenseDevice(Base, TimestampMixin):
    """A device (or SaaS client install) bound to a license.

    RLS-scoped by tenant_id (denormalized from licenses for query efficiency
    and policy simplicity).
    """

    __tablename__ = "license_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    license: Mapped["License"] = relationship(  # noqa: F821
        "License", back_populates="devices"
    )

    __table_args__ = (
        Index(
            "ix_license_devices_unique_fp",
            "license_id",
            "fingerprint",
            unique=True,
        ),
        Index("ix_license_devices_last_seen", "last_seen_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseDevice(id={self.id}, license_id={self.license_id}, "
            f"fp={self.fingerprint[:8]}…)>"
        )
