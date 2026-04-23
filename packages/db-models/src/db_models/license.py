"""License model — one per tenant, governs access to paid functionality.

Only the SHA-256 hash of the human-facing key is stored. The plaintext is
surfaced once at creation time via the admin API and never retrievable.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_REVOKED = "revoked"
STATUS_EXPIRED = "expired"

VALID_LICENSE_STATUSES: set[str] = {
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    STATUS_REVOKED,
    STATUS_EXPIRED,
}


class License(Base, TimestampMixin):
    """Tenzo license. RLS-scoped by tenant_id."""

    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA-256 hex digest of the plaintext human key",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="First two groups of the key, e.g. TNZO-K3H8P — shown in UI",
    )

    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_ACTIVE
    )
    signing_kid: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="v1",
        comment="PASETO footer kid used when signing tokens for this license",
    )

    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    max_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    fingerprint_salt: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Random per-license salt mixed into device fingerprints",
    )

    issued_by_admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    devices: Mapped[list["LicenseDevice"]] = relationship(  # noqa: F821
        "LicenseDevice",
        back_populates="license",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    activations: Mapped[list["LicenseActivation"]] = relationship(  # noqa: F821
        "LicenseActivation",
        back_populates="license",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    usage_counters: Mapped[list["LicenseUsageCounter"]] = relationship(  # noqa: F821
        "LicenseUsageCounter",
        back_populates="license",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_licenses_tenant_status", "tenant_id", "status"),
        Index("ix_licenses_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<License(id={self.id}, prefix={self.key_prefix}, "
            f"plan={self.plan}, status={self.status})>"
        )
