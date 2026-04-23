"""License activation audit log — append-only event trail."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Event types
EVENT_ACTIVATE = "activate"
EVENT_HEARTBEAT = "heartbeat"
EVENT_DEACTIVATE = "deactivate"
EVENT_DENIED = "denied"
EVENT_REVOKED = "revoked"

VALID_ACTIVATION_EVENTS: set[str] = {
    EVENT_ACTIVATE,
    EVENT_HEARTBEAT,
    EVENT_DEACTIVATE,
    EVENT_DENIED,
    EVENT_REVOKED,
}

# Denial reason codes — stable identifiers used in HTTP responses and logs.
REASON_INVALID_KEY = "INVALID_KEY"
REASON_KEY_EXPIRED = "KEY_EXPIRED"
REASON_KEY_REVOKED = "KEY_REVOKED"
REASON_KEY_SUSPENDED = "KEY_SUSPENDED"
REASON_DEVICE_LIMIT = "DEVICE_LIMIT_EXCEEDED"
REASON_RATE_LIMITED = "RATE_LIMITED"
REASON_UNKNOWN_FINGERPRINT = "UNKNOWN_FINGERPRINT"
REASON_FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"


class LicenseActivation(Base):
    """Every activate / heartbeat / denial gets one row here.

    Append-only: no updates, no deletes except via the parent license's
    cascade. RLS-scoped by tenant_id.
    """

    __tablename__ = "license_activations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
    )

    fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    license: Mapped["License"] = relationship(  # noqa: F821
        "License", back_populates="activations"
    )

    __table_args__ = (
        Index(
            "ix_license_activations_license_created",
            "license_id",
            "created_at",
        ),
        Index(
            "ix_license_activations_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, event={self.event}, "
            f"license_id={self.license_id})>"
        )
