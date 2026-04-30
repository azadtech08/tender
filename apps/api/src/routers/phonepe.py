"""PhonePe Business Payment Gateway router.

Two routers exported from this module:
  billing_router  — authenticated endpoints mounted at /api/billing/phonepe
  webhook_router  — public webhook mounted at /webhooks/phonepe

Endpoints:
  POST /api/billing/phonepe/initiate     — start a PhonePe payment for a plan
  GET  /api/billing/phonepe/status       — verify payment status from backend
  POST /webhooks/phonepe                 — server-to-server callback from PhonePe

The webhook is public (no auth) but validated by PhonePe's X-VERIFY HMAC checksum.
"""

from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from config import settings
from database import get_db_rls
from services.phonepe_service import (
    initiate_payment,
    process_webhook,
    verify_payment_status,
)

logger = structlog.get_logger(__name__)

billing_router = APIRouter()
webhook_router = APIRouter()

# ── Request / Response schemas ────────────────────────────────────────────────


class InitiatePaymentRequest(BaseModel):
    plan: str                                           # starter | pro | business
    success_path: str = "/dashboard/billing?payment=success"
    cancel_path: str = "/dashboard/billing?payment=cancelled"
    mobile_number: Optional[str] = None


class InitiatePaymentResponse(BaseModel):
    merchant_transaction_id: str
    redirect_url: str                                   # Redirect the browser here


class StatusResponse(BaseModel):
    merchant_transaction_id: str
    payment_status: str


# ── Authenticated billing endpoints ───────────────────────────────────────────


@billing_router.post("/initiate", response_model=InitiatePaymentResponse)
async def initiate_phonepe_payment(
    body: InitiatePaymentRequest,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Create a PhonePe payment session and return the hosted payment page URL."""
    _require_phonepe_configured()

    if body.plan not in ("starter", "pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plan must be one of: starter, pro, business",
        )

    base = settings.app_base_url.rstrip("/")
    # PhonePe POSTs the callback to this URL — must be publicly reachable
    webhook_base = (
        settings.phonepe_webhook_base_url.rstrip("/")
        if settings.phonepe_webhook_base_url
        else base
    )

    try:
        merchant_transaction_id, phonepe_url = await initiate_payment(
            db=db,
            tenant_id=current_user.tenant_id,
            plan=body.plan,
            redirect_url=f"{base}{body.success_path}",
            callback_url=f"{webhook_base}/webhooks/phonepe",
            mobile_number=body.mobile_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return InitiatePaymentResponse(
        merchant_transaction_id=merchant_transaction_id,
        redirect_url=phonepe_url,
    )


@billing_router.get("/status", response_model=StatusResponse)
async def check_payment_status(
    merchant_transaction_id: str,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db_rls),
):
    """Poll PhonePe to verify a payment's current status.

    Call this after the user returns from the PhonePe redirect, in case the
    server-to-server webhook has not yet been delivered.
    """
    _require_phonepe_configured()

    try:
        payment_status = await verify_payment_status(
            db=db,
            tenant_id=current_user.tenant_id,
            merchant_transaction_id=merchant_transaction_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return StatusResponse(
        merchant_transaction_id=merchant_transaction_id,
        payment_status=payment_status,
    )


# ── Public webhook endpoint ───────────────────────────────────────────────────


@webhook_router.post("/phonepe", status_code=200)
async def phonepe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_rls),
    x_verify: str = Header(alias="X-VERIFY", default=""),
):
    """Receive PhonePe server-to-server payment callback.

    PhonePe sends X-VERIFY: SHA256(base64Response + saltKey) + "###" + saltIndex.
    We validate this before trusting the payload.

    Webhook URL to register in PhonePe Business Dashboard:
      https://cataclinal-draven-unbeaming.ngrok-free.dev/webhooks/phonepe
    """
    if not _phonepe_configured():
        logger.warning("phonepe.webhook.not_configured")
        return {"received": True}

    body: dict = await request.json()

    try:
        payload = await process_webhook(
            db=db, x_verify_header=x_verify, body=body
        )
        logger.info(
            "phonepe.webhook.processed",
            code=payload.get("code"),
            merchant_transaction_id=payload.get("data", {}).get("merchantTransactionId"),
        )
    except ValueError as exc:
        logger.warning("phonepe.webhook.invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    except Exception as exc:
        logger.exception("phonepe.webhook.handler_error", error=str(exc))

    return {"received": True}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _phonepe_configured() -> bool:
    return bool(
        settings.phonepe_client_id
        and settings.phonepe_client_secret
        and settings.phonepe_pg_base_url
    )


def _require_phonepe_configured() -> None:
    if not _phonepe_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PhonePe payment gateway not configured",
        )
