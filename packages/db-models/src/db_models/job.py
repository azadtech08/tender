"""Job model — represents a scraping job."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    ForeignKey,
    Index,
    DateTime,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Job(Base, TimestampMixin):
    """Scraping job model.
    
    Represents a single run of the scraper with given parameters.
    
    Status values: pending, queued, running, completed, failed, cancelled
    
    Fields:
    - id: Primary key
    - user_id: FK to users (required)
    - keywords: JSONB array of keywords to scrape
    - cards_per_kw: Number of cards per keyword (default 3)
    - min_value: Minimum tender value filter (optional)
    - status: Current job status
    - celery_task_id: Celery task ID for this job
    - total_keywords: Total number of keywords to process
    - done_keywords: Number of keywords completed
    - total_tenders: Total tenders found
    - error_message: Error message if job failed
    - started_at: When job started running
    - completed_at: When job completed
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    keywords: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cards_per_kw: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    min_value: Mapped[Optional[float]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_preference: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, server_default="bid_end_latest"
    )
    total_keywords: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    done_keywords: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    total_tenders: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="jobs", lazy="joined")  # noqa: F821
    events: Mapped[list["JobEvent"]] = relationship(  # noqa: F821
        "JobEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    tenders: Mapped[list["Tender"]] = relationship(  # noqa: F821
        "Tender",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    schedule: Mapped[Optional["Schedule"]] = relationship(  # noqa: F821
        "Schedule",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_jobs_user_id_status", "user_id", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Job(id={self.id}, user_id={self.user_id}, status={self.status}, "
            f"total_tenders={self.total_tenders})>"
        )
