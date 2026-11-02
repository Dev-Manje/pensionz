"""Delivers notification_outbox rows. Run by the worker every few seconds
(app/worker.py); never from a request. Rows are claimed with FOR UPDATE SKIP
LOCKED so several workers never send the same message twice; failures retry
on a backoff schedule, then the row is marked failed."""
import html
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import EmailNotConfigured, send_email
from app.models.mixins import utcnow
from app.models.notification import NotificationChannel, NotificationOutbox, OutboxStatus
from app.services.notifications import PRIVATE_BODY_EVENTS, PRIVATE_LINK_EVENTS

logger = logging.getLogger("app.notifications")

RETRY_BACKOFF = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2)]
MAX_ATTEMPTS = len(RETRY_BACKOFF) + 1


def render_email(subject: str, body: str, link: str | None) -> tuple[str, str]:
    """Plain text and HTML versions with the product header (settings.brand_*)."""
    url = f"{settings.app_base_url}{link}" if link else None
    text = body + (f"\n\nOpen: {url}" if url else "") + f"\n\n— {settings.brand_name}"
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in body.split("\n") if p.strip())
    button = (
        f'<p><a href="{html.escape(url)}" style="background:{settings.brand_color};color:#fff;padding:10px 18px;'
        f'border-radius:6px;text-decoration:none;display:inline-block">Open</a></p>'
        if url else ""
    )
    page = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:auto;color:#161b26">'
        f'<div style="background:{settings.brand_color};color:#fff;padding:14px 18px;font-weight:700">{html.escape(settings.brand_name)}</div>'
        f'<div style="padding:18px;border:1px solid #dce0e6;border-top:0"><h2 style="font-size:18px">{html.escape(subject)}</h2>'
        f"{paragraphs}{button}</div></div>"
    )
    return text, page


def _send(row: NotificationOutbox) -> None:
    if row.channel == NotificationChannel.email:
        text, page = render_email(row.subject, row.body, row.link)
        send_email(row.recipient_address, row.subject, text, html=page, from_name=settings.smtp_from_name)
    else:
        raise ValueError(f"No delivery for channel '{row.channel.value}' yet")


def deliver_one(db: Session) -> bool:
    """Claims and delivers the oldest due row in its own transaction.
    Returns False when nothing is due."""
    row = db.execute(
        select(NotificationOutbox)
        .where(NotificationOutbox.status == OutboxStatus.pending, NotificationOutbox.next_attempt_at <= utcnow())
        .order_by(NotificationOutbox.next_attempt_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if row is None:
        db.rollback()
        return False

    row.attempts += 1
    try:
        _send(row)
    except EmailNotConfigured:
        row.status = OutboxStatus.skipped
        row.last_error = "SMTP not configured"
        logger.info("SMTP not configured — would have sent %s to %s", row.event, row.recipient_address)
    except Exception as exc:
        row.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if row.attempts >= MAX_ATTEMPTS:
            row.status = OutboxStatus.failed
            logger.error("Giving up on %s to %s after %d attempts", row.event, row.recipient_address, row.attempts)
        else:
            row.next_attempt_at = utcnow() + RETRY_BACKOFF[row.attempts - 1]
            logger.warning("Send %s to %s failed (attempt %d): %s", row.event, row.recipient_address, row.attempts, row.last_error)
    else:
        row.status = OutboxStatus.sent
        row.sent_at = utcnow()
        row.last_error = None
        logger.info("Sent %s to %s", row.event, row.recipient_address)
    if row.event in PRIVATE_LINK_EVENTS and row.status != OutboxStatus.pending:
        row.link = None  # a password link lives only in the email itself
    if row.event in PRIVATE_BODY_EVENTS and row.status != OutboxStatus.pending:
        row.body = "(one-time code removed after sending)"
    db.commit()
    return True


def deliver_due(db: Session, limit: int = 100) -> int:
    processed = 0
    while processed < limit and deliver_one(db):
        processed += 1
    return processed
