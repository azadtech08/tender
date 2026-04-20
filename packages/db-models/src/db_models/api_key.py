"""API key model — long-lived tokens for programmatic access."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ApiKey(Base, TimestampMixin):
    """Hashed API key for a tenant.

    The raw key is shown only once at creation time (``gem_live_<random>``).
    Only the SHA-256 hash is stored here.

    RLS scope: tenant_id scoped like every other table.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(
        String(12), nullable=False,
        comment="First 8 chars of the raw key shown in the UI for identification",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True,
        comment="SHA-256 hex digest of the full raw key",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_api_keys_hash", "key_hash", unique=True),
        Index("ix_api_keys_tenant_active", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name={self.name!r}, prefix={self.key_prefix})>"
