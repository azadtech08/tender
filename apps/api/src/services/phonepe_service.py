"""PhonePe Business Payment Gateway service — X-VERIFY / SHA256 checksum API.

PhonePe uses Merchant ID + Salt Key + Salt Index for authentication.
The dashboard labels these as "Client ID", "Client Secret", and "Client Version"
but the underlying API still uses the X-VERIFY SHA256 checksum approach.

Checksum rules:
  Pay initiation : SHA256(base64(payload) + "/pg/v1/pay" + saltKey) + "###" + saltIndex
  Status check   : SHA256("/pg/v1/status/" + merchantId + "/" + txnId + saltKey) + "###" + saltIndex
  Webhook verify : SHA256(base64Response + saltKey) + "###" + saltIndex

Environment variables (see config.py):
  PHONEPE_CLIENT_ID      — Merchant ID from PhonePe dashboard (shown as "Client ID")
  PHONEPE_CLIENT_SECRET  — Salt Key from PhonePe dashboard (shown as "Client Secret")
  PHONEPE_CLIENT_VERSION — Salt Index (shown as "Client Version", usually "1")
  PHONEPE_PG_BASE_URL    — https://api-preprod.phonepe.com/apis/pg-sandbox  (test)
                           https://api.phonepe.com/apis/hermes               (prod)
  PHONEPE_WEBHOOK_BASE_URL — public URL PhonePe can POST to (ngrok in dev)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
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

_PAY_PATH      = "/pg/v1/pay"
_STATUS_PATH   = "/pg/v1/status"


# ── Checksum helpers ──────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _salt_index() -> str:
    return str(settings.phonepe_client_version)


def _pay_checksum(base64_payload: str) -> str:
    raw = base64_payload + _PAY_PATH + settings.phonepe_client_secret
    return _sha256(raw) + "###" + _salt_index()


def _status_checksum(merchant_transaction_id: str) -> str:
    path = f"{_STATUS_PATH}/{settings.phonepe_client_id}/{merchant_transaction_id}"
    return _sha256(path + settings.phonepe_client_secret) + "###" + _salt_index()


def _webhook_checksum(base64_response: str) -> str:
    raw = base64_response + settings.phonepe_client_secret
    return _sha256(raw) + "###" + _salt_index()


def _new_merchant_transaction_id() -> str:
    return "MT" + uuid.uuid4().hex[:30].upper()


# ── Payment initiation ────────────────────────────────────────────────────────

async def initiate_payment(
    db: AsyncSession,
    tenant_id: str,
    plan: str,
    redirect_url: str,
    callback_url: str,
    mobile_number: Optional[str] = None,
) -> tuple[str, str]:
    """Initiate a PhonePe payment. Returns (merchant_transaction_id, redirect_url)."""
    amount = PHONEPE_PLAN_AMOUNTS.get(plan)
    if amount is None:
        raise ValueError(f"No PhonePe price configured for plan '{plan}'")

    merchant_transaction_id = _new_merchant_transaction_id()

    payload: dict = {
        "merchantId": settings.phonepe_client_id,
        "merchantTransactionId": merchant_transaction_id,
        "merchantUserId": f"UID{tenant_id[:28]}",
        "amount": amount,
        "redirectUrl": redirect_url,
        "redirectMode": "REDIRECT",
        "callbackUrl": callback_url,
        "paymentInstrument": {"type": "PAY_PAGE"},
    }
    if mobile_number:
        payload["mobileNumber"] = mobile_number

    # Persist PENDING row before the external call
    txn = PhonePeTransaction(
        tenant_id=tenant_id,
        plan_id=plan,
        amount=amount,
        merchant_transaction_id=merchant_transaction_id,
        payment_status=PHONEPE_STATUS_PENDING,
    )
    db.add(txn)
    await db.flush()

    base64_payload = base64.b64encode(json.dumps(payload).encode()).decode()
    x_verify = _pay_checksum(base64_payload)

    log = logger.bind(
        merchant_transaction_id=merchant_transaction_id,
        tenant_id=tenant_id,
        plan=plan,
        amount_paise=amount,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.phonepe_pg_base_url}{_PAY_PATH}",
                json={"request": base64_payload},
                headers={
                    "Content-Type": "application/json",
                    "X-VERIFY": x_verify,
                    "Accept": "application/json",
                },
            )
        resp_data = resp.json()
    except Exception as exc:
        txn.payment_status = PHONEPE_STATUS_FAILED
        log.error("phonepe.initiate.http_error", error=str(exc))
        raise RuntimeError(f"PhonePe API call failed: {exc}") from exc

    txn.raw_response = json.dumps(resp_data)

    if not resp_data.get("success"):
        txn.payment_status = PHONEPE_STATUS_FAILED
        code = resp_data.get("code", "UNKNOWN")
        message = resp_data.get("message", "unknown error")
        log.error("phonepe.initiate.api_error", code=code, message=message, response=resp_data)
        raise RuntimeError(f"PhonePe initiation failed [{code}]: {message}")

    phonepe_url: str = (
        resp_data.get("data", {})
        .get("instrumentResponse", {})
        .get("redirectInfo", {})
        .get("url", "")
    )
    if not phonepe_url:
        txn.payment_status = PHONEPE_STATUS_FAILED
        log.error("phonepe.initiate.no_redirect_url", response=resp_data)
        raise RuntimeError("PhonePe response missing redirect URL")

    log.info("phonepe.initiate.success")
    return merchant_transaction_id, phonepe_url


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

    x_verify = _status_checksum(merchant_transaction_id)
    url = (
        f"{settings.phonepe_pg_base_url}"
        f"{_STATUS_PATH}/{settings.phonepe_client_id}/{merchant_transaction_id}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={
                "X-VERIFY": x_verify,
                "X-MERCHANT-ID": settings.phonepe_client_id,
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

    PhonePe sends: { "response": "<base64-encoded-payload>" }
    Raises ValueError on bad signature (caller returns 400).
    """
    base64_response: str = body.get("response", "")
    if not base64_response:
        raise ValueError("Missing 'response' field in PhonePe webhook body")

    expected = _webhook_checksum(base64_response)
    if not hmac.compare_digest(x_verify_header.encode(), expected.encode()):
        raise ValueError("PhonePe webhook X-VERIFY signature mismatch")

    payload: dict = json.loads(base64.b64decode(base64_response).decode())
    data: dict = payload.get("data", {})
    merchant_transaction_id: str = data.get("merchantTransactionId", "")

    if not merchant_transaction_id:
        raise ValueError("Webhook payload missing merchantTransactionId")

    result = await db.execute(
        select(PhonePeTransaction).where(
            PhonePeTransaction.merchant_transaction_id == merchant_transaction_id
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        logger.warning(
            "phonepe.webhook.unknown_txn",
            merchant_transaction_id=merchant_transaction_id,
        )
        return payload

    txn.raw_response = json.dumps(payload)
    await _sync_transaction(db, txn, payload)
    return payload


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _sync_transaction(
    db: AsyncSession,
    txn: PhonePeTransaction,
    resp_data: dict,
) -> None:
    code: str = resp_data.get("code", "")
    data: dict = resp_data.get("data", {})

    txn.phonepe_transaction_id = data.get("transactionId") or txn.phonepe_transaction_id

    instrument = data.get("paymentInstrument", {})
    if instrument:
        txn.payment_method = instrument.get("type", txn.payment_method)

    if code == "PAYMENT_SUCCESS" or data.get("state") == "COMPLETED":
        txn.payment_status = PHONEPE_STATUS_SUCCESS
        await _upgrade_subscription(db, txn.tenant_id, txn.plan_id)
    elif code in ("PAYMENT_ERROR", "PAYMENT_DECLINED", "TIMED_OUT", "BAD_REQUEST"):
        txn.payment_status = PHONEPE_STATUS_FAILED

    await db.flush()
    logger.info(
        "phonepe.transaction_synced",
        merchant_transaction_id=txn.merchant_transaction_id,
        code=code,
        status=txn.payment_status,
    )


async def _upgrade_subscription(db: AsyncSession, tenant_id: str, plan: str) -> None:
    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.plan = plan
        sub.status = "active"
        sub.cancel_at_period_end = False
    else:
        db.add(Subscription(tenant_id=tenant_id, plan=plan, status="active"))
    await db.flush()
    logger.info("phonepe.subscription_upgraded", tenant_id=tenant_id, plan=plan)
