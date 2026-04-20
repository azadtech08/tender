"""Email utility using the Resend API.

Usage:
    from utils.email import send_email
    send_email(
        to=["user@example.com"],
        subject="Your daily GeM digest",
        html_body="<p>...</p>",
    )

Falls back to a structured log when RESEND_API_KEY is not configured so that
local dev / test environments don't need a live email account.
"""

from __future__ import annotations

import structlog

from config import settings

logger = structlog.get_logger(__name__)


def send_email(
    to: list[str] | str,
    subject: str,
    html_body: str,
    reply_to: str | None = None,
) -> bool:
    """Send a transactional email via Resend.

    Returns True on success, False on failure.
    Does NOT raise — callers should treat email as best-effort.
    """
    if not settings.resend_api_key:
        logger.info(
            "email.skipped_no_api_key",
            to=to,
            subject=subject,
        )
        return False

    recipients = [to] if isinstance(to, str) else to

    try:
        import httpx

        payload: dict = {
            "from": settings.email_from,
            "to": recipients,
            "subject": subject,
            "html": html_body,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        resp = httpx.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("email.sent", to=recipients, subject=subject, id=resp.json().get("id"))
        return True

    except Exception as exc:
        logger.warning("email.send_failed", to=recipients, subject=subject, error=str(exc))
        return False


def send_slack_message(webhook_url: str, text: str, blocks: list | None = None) -> bool:
    """POST a message to a Slack incoming webhook URL.

    Returns True on success, False on failure.
    """
    try:
        import httpx

        payload: dict = {"text": text}
        if blocks:
            payload["blocks"] = blocks

        resp = httpx.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("slack.sent", webhook_url=webhook_url[:40])
        return True

    except Exception as exc:
        logger.warning("slack.send_failed", webhook_url=webhook_url[:40], error=str(exc))
        return False
