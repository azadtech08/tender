"""Daily alert digest task.

Runs every day at 08:00 IST (02:30 UTC) via Celery Beat.
For each active Alert:
  1. Find tenders inserted since alert.last_triggered_at (or last 24 h)
  2. Apply alert filters (keywords, min_value, state_filter)
  3. Send email digest via Resend and/or Slack message
  4. Log an AlertDelivery row
  5. Advance last_triggered_at → now
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import Alert, AlertDelivery, Tender
from utils.email import send_email, send_slack_message

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)


def _matches_alert(alert: Alert, tender: Tender) -> bool:
    """Return True if the tender satisfies all alert filter criteria."""
    # Keyword filter — any keyword must appear in title or description
    if alert.keywords:
        kws = [k.strip().lower() for k in alert.keywords.split(",") if k.strip()]
        text = f"{tender.title or ''} {tender.description or ''}".lower()
        if not any(kw in text for kw in kws):
            return False

    # Minimum value filter
    if alert.min_value is not None and tender.tender_value is not None:
        try:
            if float(tender.tender_value) < alert.min_value:
                return False
        except (ValueError, TypeError):
            pass

    # State filter
    if alert.state_filter:
        state = (tender.state or "").lower()
        if alert.state_filter.lower() not in state:
            return False

    return True


def _build_email_html(alert: Alert, tenders: list[Tender]) -> str:
    """Render a minimal HTML digest email."""
    base_url = settings.app_base_url.rstrip("/")
    rows = ""
    for t in tenders[:50]:  # cap at 50 rows in email
        ref = t.tender_ref_no or "—"
        title = textwrap.shorten(t.title or "—", width=80)
        value = t.tender_value or "—"
        link = t.link or f"{base_url}/dashboard/tenders"
        rows += (
            f"<tr>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #ddd'>{ref}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #ddd'>{title}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #ddd;white-space:nowrap'>{value}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #ddd'>"
            f"<a href='{link}'>View</a></td>"
            f"</tr>"
        )
    more = f"<p>…and {len(tenders)-50} more. <a href='{base_url}/dashboard/tenders'>View all</a></p>" if len(tenders) > 50 else ""
    return f"""
<html><body style='font-family:sans-serif;color:#222'>
<h2>GeM Tender Digest — {alert.name}</h2>
<p>{len(tenders)} new tender(s) matching your alert criteria.</p>
<table style='border-collapse:collapse;width:100%;font-size:13px'>
  <thead>
    <tr style='background:#f4f4f4'>
      <th style='padding:6px 8px;text-align:left'>Reference</th>
      <th style='padding:6px 8px;text-align:left'>Title</th>
      <th style='padding:6px 8px;text-align:left'>Value</th>
      <th style='padding:6px 8px;text-align:left'>Link</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
{more}
<hr/>
<p style='font-size:11px;color:#999'>
  Manage alerts at <a href='{base_url}/dashboard/alerts'>{base_url}/dashboard/alerts</a>
</p>
</body></html>
"""


def _build_slack_blocks(alert: Alert, tenders: list[Tender]) -> list:
    base_url = settings.app_base_url.rstrip("/")
    lines = [f"*<{base_url}/dashboard/tenders|{t.tender_ref_no or '?'}>* — {textwrap.shorten(t.title or '', 60)}" for t in tenders[:10]]
    if len(tenders) > 10:
        lines.append(f"…and {len(tenders)-10} more")
    return [
        {"type": "header", "text": {"type": "plain_text", "text": f"GeM Digest — {alert.name}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "View Tenders"}, "url": f"{base_url}/dashboard/tenders"}]},
    ]


@celery_app.task(name="tasks.digest.send_daily_digests", ignore_result=True)
def send_daily_digests() -> None:
    """Scan active alerts and fire email/Slack digests for matching new tenders."""
    log = logger.bind(task="digest")
    log.info("digest.started")

    with Session(_engine) as session:
        alerts = session.execute(
            select(Alert).where(Alert.is_active == True)  # noqa: E712
        ).scalars().all()

        for alert in alerts:
            log_a = log.bind(alert_id=alert.id, tenant_id=alert.tenant_id)
            since = alert.last_triggered_at or (datetime.now(tz=timezone.utc) - timedelta(hours=24))

            # Find tenders for this tenant created after `since`
            tender_rows = session.execute(
                select(Tender).where(
                    Tender.tenant_id == alert.tenant_id,
                    Tender.created_at >= since,
                )
            ).scalars().all()

            matching = [t for t in tender_rows if _matches_alert(alert, t)]
            log_a.info("digest.tenders_found", total=len(tender_rows), matching=len(matching))

            if not matching:
                continue

            email_ok = slack_ok = True
            error_msg = None

            try:
                if alert.email_to:
                    recipients = [e.strip() for e in alert.email_to.split(",") if e.strip()]
                    html = _build_email_html(alert, matching)
                    email_ok = send_email(
                        to=recipients,
                        subject=f"GeM Tender Digest — {alert.name} ({len(matching)} new)",
                        html_body=html,
                    )

                if alert.slack_webhook_url:
                    slack_ok = send_slack_message(
                        webhook_url=alert.slack_webhook_url,
                        text=f"GeM Digest — {len(matching)} new tender(s) for alert '{alert.name}'",
                        blocks=_build_slack_blocks(alert, matching),
                    )

                if not email_ok or not slack_ok:
                    error_msg = "One or more channels failed (check logs)"

            except Exception as exc:
                error_msg = str(exc)
                log_a.warning("digest.delivery_error", error=error_msg)

            # Log delivery
            delivery = AlertDelivery(
                alert_id=alert.id,
                channel="email+slack" if (alert.email_to and alert.slack_webhook_url) else ("email" if alert.email_to else "slack"),
                status="ok" if error_msg is None else "error",
                tenders_count=len(matching),
                error_message=error_msg,
                delivered_at=datetime.now(tz=timezone.utc),
            )
            session.add(delivery)
            alert.last_triggered_at = datetime.now(tz=timezone.utc)
            session.commit()
            log_a.info("digest.delivered", tenders=len(matching), status=delivery.status)

    log.info("digest.finished", alerts_processed=len(alerts))
