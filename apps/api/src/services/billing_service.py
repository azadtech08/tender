"""Stripe billing service.

Responsibilities:
  - Create or retrieve a Stripe Customer for a tenant.
  - Create a Checkout Session (subscription upgrade).
  - Create a Customer Portal session (manage / cancel).
  - Record metered usage events (run / tender / ai_summary).
  - Sync subscription state from Stripe webhook payloads.

Environment variables required (see config.py):
  STRIPE_SECRET_KEY        — sk_live_... or sk_test_...
  STRIPE_WEBHOOK_SECRET    — whsec_... (for webhook signature verification)
  STRIPE_PRICE_STARTER     — price_... for Starter plan
  STRIPE_PRICE_PRO         — price_... for Pro plan
  STRIPE_PRICE_BUSINESS    — price_... for Business plan
  STRIPE_PRICE_RUN_METER   — price_... metered price for overage runs
  STRIPE_PRICE_TENDER_METER— price_... metered price for overage tenders
  STRIPE_PRICE_AI_METER    — price_... metered price for AI summaries
  APP_BASE_URL             — e.g. https://app.gemtender.com (for redirect URLs)
"""

from __future__ import annotations

import stripe
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db_models import Subscription, UsageEvent, EVENT_RUN, EVENT_TENDER, EVENT_AI_SUMMARY

logger = structlog.get_logger(__name__)


def _stripe_client() -> stripe.StripeClient:
    """Return a configured Stripe SDK client."""
    return stripe.StripeClient(settings.stripe_secret_key)


# ── Plan → Stripe price ID mapping ───────────────────────────────────────────

def _plan_price_id(plan: str) -> Optional[str]:
    mapping = {
        "starter":  settings.stripe_price_starter,
        "pro":      settings.stripe_price_pro,
        "business": settings.stripe_price_business,
    }
    return mapping.get(plan)


# ── Customer management ───────────────────────────────────────────────────────

async def get_or_create_customer(
    db: AsyncSession,
    tenant_id: str,
    email: str,
) -> str:
    """Return the Stripe customer_id for this tenant, creating one if needed."""
    sub = await _get_subscription(db, tenant_id)

    if sub and sub.stripe_customer_id:
        return sub.stripe_customer_id

    client = _stripe_client()
    customer = client.customers.create(
        params={
            "email": email,
            "metadata": {"tenant_id": tenant_id},
        }
    )
    customer_id: str = customer.id

    if sub:
        sub.stripe_customer_id = customer_id
        await db.flush()
    else:
        db.add(Subscription(
            tenant_id=tenant_id,
            stripe_customer_id=customer_id,
            plan="free",
            status="active",
        ))
        await db.flush()

    logger.info("stripe.customer_created", tenant_id=tenant_id, customer_id=customer_id)
    return customer_id


# ── Checkout ──────────────────────────────────────────────────────────────────

async def create_checkout_session(
    db: AsyncSession,
    tenant_id: str,
    email: str,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session and return its URL."""
    price_id = _plan_price_id(plan)
    if not price_id:
        raise ValueError(f"No Stripe price configured for plan '{plan}'")

    customer_id = await get_or_create_customer(db, tenant_id, email)
    client = _stripe_client()

    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"tenant_id": tenant_id, "plan": plan},
            "subscription_data": {"metadata": {"tenant_id": tenant_id}},
        }
    )
    logger.info("stripe.checkout_created", tenant_id=tenant_id, plan=plan)
    return session.url


# ── Customer Portal ───────────────────────────────────────────────────────────

async def create_portal_session(
    db: AsyncSession,
    tenant_id: str,
    email: str,
    return_url: str,
) -> str:
    """Create a Stripe Customer Portal session and return its URL."""
    customer_id = await get_or_create_customer(db, tenant_id, email)
    client = _stripe_client()
    session = client.billing_portal.sessions.create(
        params={"customer": customer_id, "return_url": return_url}
    )
    return session.url


# ── Metered usage recording ───────────────────────────────────────────────────

async def record_usage(
    db: AsyncSession,
    tenant_id: str,
    event_type: str,
    quantity: int = 1,
    job_id: Optional[int] = None,
) -> None:
    """Write a UsageEvent row.  Stripe reporting happens in a background task."""
    if event_type not in {EVENT_RUN, EVENT_TENDER, EVENT_AI_SUMMARY}:
        raise ValueError(f"Unknown event_type: {event_type}")

    db.add(UsageEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        quantity=quantity,
        job_id=job_id,
        reported_to_stripe=False,
    ))
    await db.flush()
    logger.info("usage.recorded", tenant_id=tenant_id, event_type=event_type, qty=quantity)


# ── Webhook sync ──────────────────────────────────────────────────────────────

async def sync_subscription_from_stripe(
    db: AsyncSession,
    stripe_sub: dict,
) -> None:
    """Upsert our Subscription row from a Stripe subscription object (webhook payload)."""
    stripe_sub_id: str = stripe_sub["id"]
    customer_id: str = stripe_sub["customer"]
    metadata: dict = stripe_sub.get("metadata", {})
    tenant_id: str = metadata.get("tenant_id", "")

    if not tenant_id:
        # Try to look up by customer_id.
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_customer_id == customer_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            tenant_id = sub.tenant_id

    if not tenant_id:
        logger.warning("stripe.webhook.no_tenant_id", stripe_sub_id=stripe_sub_id)
        return

    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = result.scalar_one_or_none()

    # Derive plan from the first line item's price metadata or lookup table.
    plan = _plan_from_stripe_sub(stripe_sub)
    status: str = stripe_sub.get("status", "active")
    period_end_ts = stripe_sub.get("current_period_end")
    period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    )
    cancel_at_end: bool = stripe_sub.get("cancel_at_period_end", False)

    if sub:
        sub.stripe_subscription_id = stripe_sub_id
        sub.stripe_customer_id = customer_id
        sub.plan = plan
        sub.status = status
        sub.current_period_end = period_end
        sub.cancel_at_period_end = cancel_at_end
    else:
        db.add(Subscription(
            tenant_id=tenant_id,
            stripe_customer_id=customer_id,
            stripe_subscription_id=stripe_sub_id,
            plan=plan,
            status=status,
            current_period_end=period_end,
            cancel_at_period_end=cancel_at_end,
        ))

    await db.flush()
    logger.info(
        "stripe.subscription_synced",
        tenant_id=tenant_id,
        plan=plan,
        status=status,
    )


def _plan_from_stripe_sub(stripe_sub: dict) -> str:
    """Determine our plan slug from the Stripe subscription's price IDs."""
    price_to_plan = {
        settings.stripe_price_starter:  "starter",
        settings.stripe_price_pro:      "pro",
        settings.stripe_price_business: "business",
    }
    for item in stripe_sub.get("items", {}).get("data", []):
        price_id = item.get("price", {}).get("id", "")
        if price_id in price_to_plan:
            return price_to_plan[price_id]
    return "free"


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_subscription(db: AsyncSession, tenant_id: str) -> Optional[Subscription]:
    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_current_plan(db: AsyncSession, tenant_id: str) -> Subscription:
    """Return the subscription for this tenant, creating a free one if absent."""
    sub = await _get_subscription(db, tenant_id)
    if sub is None:
        sub = Subscription(tenant_id=tenant_id, plan="free", status="active")
        db.add(sub)
        await db.flush()
    return sub
