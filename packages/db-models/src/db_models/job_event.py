"""JobEvent model — audit log entries for jobs."""

from datetime import datetime

from sqlalchemy import String, ForeignKey, Index, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class JobEvent(Base):
    """Event log entry for a job.
    
    Event types: status_change, keyword_start, keyword_done, card_scraped, 
                 pdf_downloaded, error, complete
    
    Fields:
    - id: Primary key
    - job_id: FK to jobs (required)
    - event_type: Type of event
    - payload: JSONB event data
    - created_at: When event occurred
    """

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="events", lazy="joined")  # noqa: F821

    __table_args__ = (
        Index("ix_job_events_job_id_created_at", "job_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<JobEvent(id={self.id}, job_id={self.job_id}, type={self.event_type})>"
