"""Outbound webhooks router — tenant-defined HTTP callbacks.

Endpoints:
  GET    /api/webhooks             — list webhooks
  POST   /api/webhooks             — register webhook
  PATCH  /api/webhooks/{id}        — update webhook
  DELETE /api/webhooks/{id}        — remove webhook
  POST   /api/webhooks/{id}/test   — send a test ping

Supported events: job.completed  job.failed  tender.new
Delivery signature: HMAC-SHA256 in header X-Gem-Signature.
"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Annotated, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db
from db_models import OutboundWebhook, WebhookDelivery

logger = structlog.get_logger(__name__)
router = APIRouter()

SUPPORTED_EVENTS = {"job.completed", "job.failed", "tender.new"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., description="HTTPS URL that will receive POST requests")
    events: list[str] = Field(..., min_length=1)
    is_active: bool = True

    def validate_events(self) -> None:
        bad = set(self.events) - SUPPORTED_EVENTS
        if bad:
            raise ValueError(f"Unknown events: {bad}. Supported: {SUPPORTED_EVENTS}")


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    events: list[str]
    is_active: bool
    last_fired_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookCreatedResponse(WebhookResponse):
    """Includes signing secret — shown only once at creation."""
    secret: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_webhook(db: AsyncSession, wh_id: int, tenant_id: str) -> OutboundWebhook:
    result = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.id == wh_id,
            OutboundWebhook.tenant_id == tenant_id,
        )
    )
    wh = result.scalar_one_or_none()
    if wh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return wh


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _fire(wh: OutboundWebhook, event: str, payload: dict, db: AsyncSession) -> int:
    """POST payload to the webhook URL, log the result. Returns HTTP status."""
    body = json.dumps({"event": event, "data": payload}).encode()
    signature = _sign(wh.secret, body)
    http_status = 0
    response_body = None
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                wh.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gem-Signature": signature,
                    "X-Gem-Event": event,
                },
            )
        http_status = resp.status_code
        response_body = resp.text[:500]
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("webhook.fire_failed", webhook_id=wh.id, event=event, error=error_msg)

    delivery = WebhookDelivery(
        webhook_id=wh.id,
        event=event,
        http_status=http_status,
        response_body=response_body,
        error_message=error_msg,
        fired_at=datetime.now(tz=timezone.utc),
    )
    db.add(delivery)
    wh.last_fired_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return http_status


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WebhookResponse]:
    result = await db.execute(
        select(OutboundWebhook)
        .where(OutboundWebhook.tenant_id == current_user.tenant_id)
        .order_by(OutboundWebhook.created_at.desc())
    )
    return [WebhookResponse.model_validate(w) for w in result.scalars().all()]


@router.post("", response_model=WebhookCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookCreatedResponse:
    bad = set(body.events) - SUPPORTED_EVENTS
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown events: {bad}. Supported: {sorted(SUPPORTED_EVENTS)}",
        )
    secret = secrets.token_hex(32)
    wh = OutboundWebhook(
        tenant_id=current_user.tenant_id,
        name=body.name,
        url=body.url,
        events=body.events,
        secret=secret,
        is_active=body.is_active,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return WebhookCreatedResponse(
        id=wh.id,
        name=wh.name,
        url=wh.url,
        events=wh.events,
        is_active=wh.is_active,
        last_fired_at=wh.last_fired_at,
        created_at=wh.created_at,
        secret=secret,   # shown once
    )


@router.patch("/{wh_id}", response_model=WebhookResponse)
async def update_webhook(
    wh_id: int,
    body: WebhookUpdate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookResponse:
    wh = await _get_webhook(db, wh_id, current_user.tenant_id)
    if body.events is not None:
        bad = set(body.events) - SUPPORTED_EVENTS
        if bad:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown events: {bad}",
            )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(wh, field, value)
    wh.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(wh)
    return WebhookResponse.model_validate(wh)


@router.delete("/{wh_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    wh_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    wh = await _get_webhook(db, wh_id, current_user.tenant_id)
    await db.delete(wh)
    await db.commit()


@router.post("/{wh_id}/test", status_code=status.HTTP_200_OK)
async def test_webhook(
    wh_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Fire a test ping to the webhook URL."""
    wh = await _get_webhook(db, wh_id, current_user.tenant_id)
    http_status = await _fire(
        wh, "ping", {"message": "GeM Tender webhook test ping"}, db
    )
    return {"http_status": http_status, "success": 200 <= http_status < 300}
