"""Synchronous SMTP sending (used from Celery workers)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def send_plain_text(to_addr: str, subject: str, body: str) -> None:
    """
    Send a plain-text email. No-op with a log line if ``SMTP_HOST`` is unset.
    """
    settings = get_settings()
    if not settings.SMTP_HOST:
        logger.info("SMTP_HOST not set; skipping email to %s (%s)", to_addr, subject)
        return

    sender = settings.SMTP_FROM or settings.SMTP_USER
    if not sender:
        logger.error("SMTP_FROM / SMTP_USER not set; cannot send email.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
