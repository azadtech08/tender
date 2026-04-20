"""Outbound webhook fire task.

Called from scrape_job after a job completes or fails.
Sends HMAC-SHA256 signed POST requests to all active tenant webhooks
subscribed to the relevant event.

Delivery is best-effort — failures are logged to webhook_deliveries but
do not block the scrape job result.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import OutboundWebhook, WebhookDelivery

logger = structlog.get_logger(__name__)

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _fire_one(wh: OutboundWebhook, event: str, payload: dict, session: Session) -> None:
    body = json.dumps({"event": event, "data": payload}).encode()
    signature = _sign(wh.secret, body)
    http_status = 0
    response_body: str | None = None
    error_msg: str | None = None

    try:
        with httpx.Client(timeout=settings.webhook_timeout_seconds) as client:
            resp = client.post(
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
        logger.info("webhook.fired", webhook_id=wh.id, event=event, status=http_status)
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
    session.add(delivery)
    wh.last_fired_at = datetime.now(tz=timezone.utc)
    session.commit()


@celery_app.task(name="tasks.webhook_fire.fire_job_event", ignore_result=True)
def fire_job_event(
    tenant_id: str,
    event: str,
    payload: dict,
) -> None:
    """Fire `event` to all active tenant webhooks subscribed to it.

    Args:
        tenant_id: The tenant whose webhooks should receive the event.
        event:     One of  job.completed | job.failed | tender.new
        payload:   Arbitrary JSON-serialisable dict to include under "data".
    """
    log = logger.bind(tenant_id=tenant_id, event=event)
    log.info("webhook_fire.started")

    with Session(_engine) as session:
        hooks = session.execute(
            select(OutboundWebhook).where(
                OutboundWebhook.tenant_id == tenant_id,
                OutboundWebhook.is_active == True,  # noqa: E712
            )
        ).scalars().all()

        for wh in hooks:
            if event not in (wh.events or []):
                continue
            try:
                _fire_one(wh, event, payload, session)
            except Exception as exc:
                log.warning("webhook_fire.unhandled", webhook_id=wh.id, error=str(exc))

    log.info("webhook_fire.done", hooks_checked=len(hooks))
