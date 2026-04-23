"""Admin audit log — append-only trail of cross-tenant admin actions.

Intentionally NOT tenant-scoped. Access is gated by admin role at the
application layer (see routers/admin_licenses.py when Phase 3 lands).
``target_tenant_id`` is denormalized purely for filtering in the admin UI.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

ACTION_LICENSE_CREATE = "license.create"
ACTION_LICENSE_REVOKE = "license.revoke"
ACTION_LICENSE_SUSPEND = "license.suspend"
ACTION_LICENSE_REACTIVATE = "license.reactivate"
ACTION_LICENSE_EXTEND = "license.extend"
ACTION_DEVICE_REVOKE = "device.revoke"
ACTION_KEY_ROTATE = "key.rotate"

VALID_ADMIN_ACTIONS: set[str] = {
    ACTION_LICENSE_CREATE,
    ACTION_LICENSE_REVOKE,
    ACTION_LICENSE_SUSPEND,
    ACTION_LICENSE_REACTIVATE,
    ACTION_LICENSE_EXTEND,
    ACTION_DEVICE_REVOKE,
    ACTION_KEY_ROTATE,
}


class AdminAuditLog(Base):
    """One row per admin mutation. Never UPDATE or DELETE."""

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Local users.id when known. NULL for Clerk-only admins.",
    )
    admin_subject: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Auth-provider subject — Clerk user_id or stringified local users.id",
    )
    admin_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    target_tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    target_license_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("licenses.id", ondelete="SET NULL"),
        nullable=True,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_admin_audit_admin_created", "admin_id", "created_at"),
        Index("ix_admin_audit_target_license", "target_license_id"),
        Index(
            "ix_admin_audit_target_tenant_created",
            "target_tenant_id",
            "created_at",
        ),
        Index(
            "ix_admin_audit_subject_created",
            "admin_subject",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AdminAuditLog(id={self.id}, admin_id={self.admin_id}, "
            f"action={self.action})>"
        )
