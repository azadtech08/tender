"""Stripe webhook handler.

Receives POST /webhooks/stripe and processes subscription lifecycle events.

Security: every request is verified against STRIPE_WEBHOOK_SECRET using
Stripe's svix-based signature (stripe.WebhookSignature.verify_header).
Requests that fail signature verification return 400 immediately.

Events handled:
  customer.subscription.created    → upsert subscription row
  customer.subscription.updated    → upsert subscription row
  customer.subscription.deleted    → set status=cancelled
  checkout.session.completed       → upsert from embedded subscription
  invoice.payment_succeeded        → mark subscription active
  invoice.payment_failed           → mark subscription past_due
"""

import stripe
import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db_rls
from db_models import Subscription
from services.billing_service import sync_subscription_from_stripe
from fastapi import Depends

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature", default=""),
    db: AsyncSession = Depends(get_db_rls),
):
    """Receive and process Stripe webhook events."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhooks not configured",
        )

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("stripe.webhook.invalid_signature", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        )

    event_type: str = event["type"]
    log = logger.bind(stripe_event_type=event_type, stripe_event_id=event["id"])
    log.info("stripe.webhook.received")

    try:
        if event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            await sync_subscription_from_stripe(db, event["data"]["object"])

        elif event_type == "customer.subscription.deleted":
            sub_obj = event["data"]["object"]
            result = await db.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == sub_obj["id"]
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = "cancelled"
                sub.plan = "free"
            log.info("stripe.subscription_cancelled")

        elif event_type == "checkout.session.completed":
            session_obj = event["data"]["object"]
            if session_obj.get("subscription"):
                # Fetch the full subscription from Stripe for accurate data.
                client = stripe.StripeClient(settings.stripe_secret_key)
                full_sub = client.subscriptions.retrieve(session_obj["subscription"])
                await sync_subscription_from_stripe(db, full_sub)

        elif event_type == "invoice.payment_succeeded":
            sub_id = event["data"]["object"].get("subscription")
            if sub_id:
                result = await db.execute(
                    select(Subscription).where(
                        Subscription.stripe_subscription_id == sub_id
                    )
                )
                sub = result.scalar_one_or_none()
                if sub and sub.status in ("past_due", "unpaid"):
                    sub.status = "active"

        elif event_type == "invoice.payment_failed":
            sub_id = event["data"]["object"].get("subscription")
            if sub_id:
                result = await db.execute(
                    select(Subscription).where(
                        Subscription.stripe_subscription_id == sub_id
                    )
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = "past_due"
            log.warning("stripe.invoice_payment_failed")

        else:
            log.debug("stripe.webhook.unhandled")

    except Exception as exc:
        log.exception("stripe.webhook.handler_error", error=str(exc))
        # Return 200 so Stripe does not retry — we log the error internally.

    return {"received": True}
