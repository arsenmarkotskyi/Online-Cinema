"""Stripe webhook: mark orders paid after Checkout completes."""

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from stripe import SignatureVerificationError

from src.config.settings import get_settings
from src.database.models import (
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentItem,
    PaymentStatus,
)
from src.database.session import get_db

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STRIPE_WEBHOOK_SECRET is not configured.",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature"
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload") from e
    except SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await _fulfill_checkout_session(db, session)

    return {"received": True}


async def _fulfill_checkout_session(db: AsyncSession, session: dict) -> None:
    if session.get("payment_status") != "paid":
        return

    meta = session.get("metadata") or {}
    raw_oid = meta.get("order_id")
    if not raw_oid:
        return
    order_id = int(raw_oid)

    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.movie),
            selectinload(Order.user),
        )
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        return
    if order.status != OrderStatus.PENDING:
        return

    amount_total = session.get("amount_total")
    if amount_total is None:
        return

    expected_cents = int(
        round(sum(float(oi.price_at_order) for oi in order.items) * 100)
    )
    if int(amount_total) != expected_cents:
        # Do not mark paid if totals diverge — requires manual reconciliation
        return

    existing = await db.execute(
        select(Payment).where(Payment.external_payment_id == session["id"])
    )
    if existing.scalar_one_or_none():
        return

    session_id = session["id"]
    total_amount = sum(float(oi.price_at_order) for oi in order.items)

    payment = Payment(
        user_id=order.user_id,
        order_id=order.id,
        status=PaymentStatus.SUCCESSFUL,
        amount=total_amount,
        external_payment_id=session_id,
    )
    db.add(payment)
    await db.flush()

    for oi in order.items:
        db.add(
            PaymentItem(
                payment_id=payment.id,
                order_item_id=oi.id,
                price_at_payment=float(oi.price_at_order),
            )
        )

    user_email = order.user.email if order.user else None
    lines_summary = "\n".join(
        (
            f"- {oi.movie.name if oi.movie else f'Movie #{oi.movie_id}'}: "
            f"{float(oi.price_at_order):.2f}"
        )
        for oi in (order.items or [])
    )

    order.status = OrderStatus.PAID
    await db.commit()

    if user_email:
        from src.worker.mail_tasks import send_order_paid_email

        send_order_paid_email.delay(  # type: ignore[attr-defined]
            user_email, order.id, total_amount, lines_summary
        )
