"""PhonePe transaction model — one row per payment attempt."""

from typing import Optional

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

# Payment status constants (mirror PhonePe state machine)
PHONEPE_STATUS_PENDING = "PENDING"
PHONEPE_STATUS_SUCCESS = "SUCCESS"
PHONEPE_STATUS_FAILED = "FAILED"
PHONEPE_STATUS_CANCELLED = "CANCELLED"

VALID_PHONEPE_STATUSES = {
    PHONEPE_STATUS_PENDING,
    PHONEPE_STATUS_SUCCESS,
    PHONEPE_STATUS_FAILED,
    PHONEPE_STATUS_CANCELLED,
}

# Plan prices in paise (1 INR = 100 paise) — must match CLAUDE.md pricing table
PHONEPE_PLAN_AMOUNTS: dict[str, int] = {
    "starter": 149900,   # ₹1,499
    "pro": 499900,       # ₹4,999
    "business": 1499900, # ₹14,999
}


class PhonePeTransaction(Base, TimestampMixin):
    """Audit record for every PhonePe payment attempt.

    Created with status=PENDING when payment is initiated.
    Updated by webhook callback or status-check polling.
    On SUCCESS the billing service upgrades the tenant's subscription.
    """

    __tablename__ = "phonepe_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    plan_id: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise

    # Our own transaction ID sent to PhonePe (≤38 chars, URL-safe)
    merchant_transaction_id: Mapped[str] = mapped_column(
        String(38), nullable=False, unique=True, index=True
    )
    # Transaction ID assigned by PhonePe (populated after callback/status check)
    phonepe_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )

    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PHONEPE_STATUS_PENDING
    )
    # e.g. "UPI", "CARD", "NET_BANKING", "WALLET" — set from webhook payload
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Full JSON from the latest PhonePe response (for audit / support)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_phonepe_transactions_tenant_status", "tenant_id", "payment_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<PhonePeTransaction(mtxn={self.merchant_transaction_id}, "
            f"plan={self.plan_id}, status={self.payment_status})>"
        )
