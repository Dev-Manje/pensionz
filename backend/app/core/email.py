import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings

logger = logging.getLogger("app.email")


class EmailNotConfigured(Exception):
    """smtp_host is empty — there is nowhere to send to."""


def send_email(to_email: str, subject: str, body: str, html: str | None = None, from_name: str | None = None) -> None:
    """Sends one email over SMTP: plain text, plus an HTML alternative when
    given. Raises on any failure (including EmailNotConfigured) so the
    caller — the outbox delivery worker, never a request handler — can
    record the error and retry."""
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not set")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, settings.smtp_from_email)) if from_name else settings.smtp_from_email
    message["To"] = to_email
    message.set_content(body)
    if html is not None:
        message.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
