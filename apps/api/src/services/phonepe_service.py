"""PhonePe Business Payment Gateway service — OAuth 2.0 new API.

Credentials from PhonePe Business Dashboard → Developer Settings → API Keys:
  PHONEPE_CLIENT_ID      — Client ID (NOT merchant ID)
  PHONEPE_CLIENT_SECRET  — Client Secret
  PHONEPE_CLIENT_VERSION — Client Version (usually 1)
  PHONEPE_AUTH_BASE_URL  — Token endpoint base
                           Test: https://api-preprod.phonepe.com/apis/pg-sandbox
                           Prod: https://api.phonepe.com/apis/pg
  PHONEPE_PG_BASE_URL    — Payment API base
                           Test: https://api-preprod.phonepe.com/apis/pg-sandbox
                           Prod: https://api.phonepe.com/apis/pg
  PHONEPE_WEBHOOK_BASE_URL — public URL PhonePe can POST to (ngrok in dev)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db_models import Subscription
from db_models.phonepe_transaction import (
    PHONEPE_PLAN_AMOUNTS,
    PHONEPE_STATUS_FAILED,
    PHONEPE_STATUS_PENDING,
    PHONEPE_STATUS_SUCCESS,
    PhonePeTransaction,
)

logger = structlog.get_logger(__name__)

_TOKEN_PATH  = "/v1/oauth/token"
_PAY_PATH    = "/checkout/v2/pay"
_ORDER_PATH  = "/checkout/v2/order"   # status: {base}/{_ORDER_PATH}/{merchantOrderId}/status

# In-process token cache: reuse until 60s before expiry
_token_cache: dict = {"access_token": None, "expires_at": 0}


# ── OAuth token management ────────────────────────────────────────────────────

async def _get_access_token() -> str:
    now_ms = int(time.time() * 1000)
    if _token_cache["access_token"] and _token_cache["expires_at"] > now_ms + 60_000:
        return _token_cache["access_token"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.phonepe_auth_base_url}{_TOKEN_PATH}",
            data={
                "client_id": settings.phonepe_client_id,
                "client_secret": settings.phonepe_client_secret,
                "client_version": str(settings.phonepe_client_version),
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    # PhonePe returns expiresAt in milliseconds (epoch)
    _token_cache["expires_at"] = data.get("expiresAt", now_ms + 1_800_000)
    return _token_cache["access_token"]


def _new_merchant_order_id() -> str:
    return "MT" + uuid.uuid4().hex[:30].upper()


# ── Webhook signature helper ──────────────────────────────────────────────────

def _webhook_checksum(payload_str: str) -> str:
    """New API: SHA256(payload_string + client_secret) + '###' + client_version."""
    raw = payload_str + settings.phonepe_client_secret
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return digest + "###" + str(settings.phonepe_client_version)


# ── Payment initiation ────────────────────────────────────────────────────────

async def initiate_payment(
    db: AsyncSession,
    tenant_id: str,
    plan: str,
    redirect_url: str,
    callback_url: str,
    mobile_number: Optional[str] = None,
) -> tuple[str, str]:
    """Initiate a PhonePe payment. Returns (merchant_order_id, redirect_url)."""
    amount = PHONEPE_PLAN_AMOUNTS.get(plan)
    if amount is None:
        raise ValueError(f"No PhonePe price configured for plan '{plan}'")

    merchant_order_id = _new_merchant_order_id()

    payload: dict = {
        "merchantOrderId": merchant_order_id,
        "amount": amount,
        "merchantUserId": f"UID{tenant_id[:28]}",
        "expireAfter": 1200,
        "paymentFlow": {
            "type": "PG_CHECKOUT",
            "merchantUrls": {
                "redirectUrl": redirect_url,
                "callbackUrl": callback_url,
            },
        },
    }
    if mobile_number:
        payload["mobileNumber"] = mobile_number

    txn = PhonePeTransaction(
        tenant_id=tenant_id,
        plan_id=plan,
        amount=amount,
        merchant_transaction_id=merchant_order_id,
        payment_status=PHONEPE_STATUS_PENDING,
    )
    db.add(txn)
    await db.flush()

    log = logger.bind(
        merchant_order_id=merchant_order_id,
        tenant_id=tenant_id,
        plan=plan,
        amount_paise=amount,
    )

    try:
        token = await _get_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.phonepe_pg_base_url}{_PAY_PATH}",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"O-Bearer {token}",
                    "Accept": "application/json",
                },
            )
        resp_data = resp.json()
    except Exception as exc:
        txn.payment_status = PHONEPE_STATUS_FAILED
        log.error("phonepe.initiate.http_error", error=str(exc))
        raise RuntimeError(f"PhonePe API call failed: {exc}") from exc

    txn.raw_response = json.dumps(resp_data)

    state = resp_data.get("state", "")
    if state not in ("PENDING", "INITIATED"):
        txn.payment_status = PHONEPE_STATUS_FAILED
        code = resp_data.get("code", resp_data.get("errorCode", "UNKNOWN"))
        message = resp_data.get("message", resp_data.get("description", "unknown error"))
        log.error("phonepe.initiate.api_error", code=code, message=message, response=resp_data)
        raise RuntimeError(f"PhonePe initiation failed [{code}]: {message}")

    # New API returns redirectUrl at top level
    phonepe_url: str = resp_data.get("redirectUrl", "")
    if not phonepe_url:
        txn.payment_status = PHONEPE_STATUS_FAILED
        log.error("phonepe.initiate.no_redirect_url", response=resp_data)
        raise RuntimeError("PhonePe response missing redirect URL")

    # Store PhonePe's internal orderId if provided
    txn.phonepe_transaction_id = resp_data.get("orderId")

    log.info("phonepe.initiate.success")
    return merchant_order_id, phonepe_url


# ── Payment status verification ───────────────────────────────────────────────

async def verify_payment_status(
    db: AsyncSession,
    tenant_id: str,
    merchant_transaction_id: str,
) -> str:
    """Poll PhonePe status API and sync our DB record. Returns payment_status."""
    result = await db.execute(
        select(PhonePeTransaction).where(
            PhonePeTransaction.merchant_transaction_id == merchant_transaction_id,
            PhonePeTransaction.tenant_id == tenant_id,
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise ValueError(f"Transaction not found: {merchant_transaction_id}")

    token = await _get_access_token()
    url = f"{settings.phonepe_pg_base_url}{_ORDER_PATH}/{merchant_transaction_id}/status"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"O-Bearer {token}",
                "Accept": "application/json",
            },
        )

    resp_data = resp.json()
    txn.raw_response = json.dumps(resp_data)
    await _sync_transaction(db, txn, resp_data)

    logger.info(
        "phonepe.status_checked",
        merchant_transaction_id=merchant_transaction_id,
        status=txn.payment_status,
    )
    return txn.payment_status


# ── Webhook processing ────────────────────────────────────────────────────────

async def process_webhook(
    db: AsyncSession,
    x_verify_header: str,
    body: dict,
) -> dict:
    """Validate X-VERIFY signature and process PhonePe server callback.

    PhonePe new API sends JSON body directly; signature is over the serialised body.
    Raises ValueError on bad signature (caller returns 400).
    """
    body_str = json.dumps(body, separators=(",", ":"), sort_keys=True)
    expected = _webhook_checksum(body_str)
    if not hmac.compare_digest(x_verify_header.encode(), expected.encode()):
        raise ValueError("PhonePe webhook X-VERIFY signature mismatch")

    # New API webhook payload shape: {event, merchantOrderId, orderId, state, amount, ...}
    merchant_order_id: str = body.get("merchantOrderId", "")
    if not merchant_order_id:
        raise ValueError("Webhook payload missing merchantOrderId")

    result = await db.execute(
        select(PhonePeTransaction).where(
            PhonePeTransaction.merchant_transaction_id == merchant_order_id
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        logger.warning("phonepe.webhook.unknown_txn", merchant_order_id=merchant_order_id)
        return body

    txn.raw_response = json.dumps(body)
    await _sync_transaction(db, txn, body)
    return body


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _sync_transaction(
    db: AsyncSession,
    txn: PhonePeTransaction,
    resp_data: dict,
) -> None:
    state: str = resp_data.get("state", "")

    txn.phonepe_transaction_id = (
        resp_data.get("orderId") or txn.phonepe_transaction_id
    )

    # Payment method from new API: paymentDetails[0].paymentMode
    details = resp_data.get("paymentDetails", [])
    if details and isinstance(details, list):
        txn.payment_method = details[0].get("paymentMode", txn.payment_method)

    if state == "COMPLETED":
        txn.payment_status = PHONEPE_STATUS_SUCCESS
        await _upgrade_subscription(db, txn.tenant_id, txn.plan_id)
    elif state in ("FAILED", "CANCELLED", "EXPIRED", "ERROR"):
        txn.payment_status = PHONEPE_STATUS_FAILED

    await db.flush()
    logger.info(
        "phonepe.transaction_synced",
        merchant_transaction_id=txn.merchant_transaction_id,
        state=state,
        status=txn.payment_status,
    )


async def _upgrade_subscription(db: AsyncSession, tenant_id: str, plan: str) -> None:
    period_end = datetime.now(timezone.utc) + timedelta(days=30)

    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.plan = plan
        sub.status = "active"
        sub.cancel_at_period_end = False
        sub.current_period_end = period_end
    else:
        db.add(Subscription(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            current_period_end=period_end,
        ))
    await db.flush()
    logger.info(
        "phonepe.subscription_upgraded",
        tenant_id=tenant_id,
        plan=plan,
        period_end=period_end.isoformat(),
    )
