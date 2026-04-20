"""Schedule model — recurring job schedules."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, Boolean, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Schedule(Base, TimestampMixin):
    """Recurring schedule for a job.
    
    Fields:
    - id: Primary key
    - job_id: FK to jobs (unique, one schedule per job)
    - cron_hour: Hour to run (0-23)
    - cron_minute: Minute to run (0-59)
    - is_active: Whether this schedule is active
    - last_run_at: Timestamp of last execution
    - next_run_at: Timestamp of next scheduled execution
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    cron_hour: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    cron_minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="schedule", lazy="joined")  # noqa: F821

    __table_args__ = (
        Index("ix_schedules_job_id_is_active", "job_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<Schedule(id={self.id}, job_id={self.job_id}, "
            f"time={self.cron_hour:02d}:{self.cron_minute:02d}, "
            f"active={self.is_active})>"
        )
