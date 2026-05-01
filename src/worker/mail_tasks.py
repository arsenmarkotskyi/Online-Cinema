"""Celery tasks: transactional email."""

from __future__ import annotations

import logging

from src.config.settings import get_settings
from src.email.smtp_send import send_plain_text
from src.worker.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="online_cinema.mail.send_activation")
def send_activation_email(to_email: str, token: str) -> None:
    settings = get_settings()
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    link = f"{base}/auth/activate/{token}"
    body = (
        "Welcome to Online Cinema.\n\n"
        f"Activate your account by opening this link in your browser:\n{link}\n\n"
        "If you did not register, ignore this message."
    )
    try:
        send_plain_text(to_email, "Activate your account", body)
    except Exception:
        logger.exception("send_activation_email failed to=%s", to_email)
        raise


@app.task(name="online_cinema.mail.send_password_reset")
def send_password_reset_email(to_email: str, token: str) -> None:
    settings = get_settings()
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    link = f"{base}/docs"
    body = (
        "You requested a password reset.\n\n"
        "Use token (valid 24h) with POST /auth/reset-password/{token}:\n\n"
        f"{token}\n\n"
        f"API docs: {link}\n\n"
        "If you did not request this, ignore this email."
    )
    try:
        send_plain_text(to_email, "Password reset", body)
    except Exception:
        logger.exception("send_password_reset_email failed to=%s", to_email)
        raise


@app.task(name="online_cinema.mail.send_order_paid")
def send_order_paid_email(
    to_email: str,
    order_id: int,
    total_amount: float,
    lines_summary: str,
) -> None:
    body = (
        f"Payment received. Order #{order_id} is paid.\n\n"
        f"Total: {total_amount:.2f}\n\n"
        f"Items:\n{lines_summary}\n\n"
        "Thank you for your purchase."
    )
    try:
        send_plain_text(to_email, f"Order #{order_id} confirmed", body)
    except Exception:
        logger.exception(
            "send_order_paid_email failed to=%s order_id=%s", to_email, order_id
        )
        raise
