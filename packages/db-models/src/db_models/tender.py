"""Tender model — represents scraped tender data."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    ForeignKey,
    Index,
    Date,
    DateTime,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Tender(Base, TimestampMixin):
    """Tender record model.
    
    Stores all 23 fields from the golden contract + metadata.
    
    The 23 core fields (in order):
    1. S.No (auto-generated per job)
    2. Keyword
    3. Tender Reference No
    4. Tender Type
    5. Published Date
    6. Bid Submission End Date
    7. Title
    8. Description
    9. Cleaned BOQ
    10. Organisation
    11. Ministry
    12. Tender Value
    13. EMD
    14. State
    15. Pincode
    16. Delivery Period
    17. Product Type
    18. Exemption
    19. Email
    20. IT Relevant
    21. Quantity
    22. Link
    23. Scraped Date
    
    Additional fields:
    - job_id: FK to jobs
    - pdf_s3_key: S3/R2 location of PDF
    """

    __tablename__ = "tenders"

    # Primary key and FK
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core 23 fields (in contract order)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tender_ref_no: Mapped[str] = mapped_column(String(100), nullable=False)
    tender_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    published_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    bid_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cleaned_boq: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organisation: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ministry: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tender_value: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    emd: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    delivery_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    product_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exemption: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    it_relevant: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    quantity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_date: Mapped[Optional[date]] = mapped_column(Date, default=date.today)

    # Additional metadata
    pdf_s3_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="tenders", lazy="joined")  # noqa: F821

    __table_args__ = (
        Index("uq_tenders_ref_job", "tender_ref_no", "job_id", unique=True),
        Index("ix_tenders_job_id_keyword", "job_id", "keyword"),
        Index("ix_tenders_scraped_date", "scraped_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Tender(id={self.id}, ref_no={self.tender_ref_no}, "
            f"job_id={self.job_id}, keyword={self.keyword})>"
        )

    def to_export_row(self, row_number: int) -> dict:
        """Convert tender to export row (23 columns).
        
        Args:
            row_number: S.No for this row
            
        Returns:
            Dict with keys matching XLSX column headers
        """
        from datetime import datetime as dt_cls

        return {
            "S.No": row_number,
            "Keyword": self.keyword,
            "Tender Reference No": self.tender_ref_no,
            "Tender Type": self.tender_type or "",
            "Published Date": self.published_date.strftime("%d-%m-%Y") if self.published_date else "",
            "Bid Submission End Date": (
                self.bid_end_date.strftime("%d-%m-%Y %H:%M") if self.bid_end_date else ""
            ),
            "Title": self.title or "",
            "Description": self.description or "",
            "Cleaned BOQ": self.cleaned_boq or "",
            "Organisation": self.organisation or "",
            "Ministry": self.ministry or "",
            "Tender Value": float(self.tender_value) if self.tender_value else "",
            "EMD": float(self.emd) if self.emd else "",
            "State": self.state or "",
            "Pincode": self.pincode or "",
            "Delivery Period": self.delivery_period or "",
            "Product Type": self.product_type or "",
            "Exemption": self.exemption or "",
            "Email": self.email or "",
            "IT Relevant": self.it_relevant or "",
            "Quantity": self.quantity or "",
            "Link": self.link or "",
            "Scraped Date": self.scraped_date.strftime("%d-%m-%Y") if self.scraped_date else "",
        }
