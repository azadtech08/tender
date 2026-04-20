"""User model — represents registered users."""

from typing import Optional

from sqlalchemy import String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User account model.
    
    Fields:
    - id: Primary key, auto-incrementing
    - email: Unique email address (required for login)
    - password_hash: bcrypt hash of password
    - display_name: User's display name
    - is_active: Soft delete flag
    - created_at, updated_at: Timestamps
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(  # noqa: F821
        "Job",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, display_name={self.display_name})>"
