"""User-facing payment endpoints (Stripe Checkout)."""

from datetime import datetime
from typing import Any, cast

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from stripe import StripeError

from src.auth.dependencies import get_current_active_user
from src.config.settings import get_settings
from src.database.models import (
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentItem,
    User,
)
from src.database.session import get_db
from src.schemas.payments import (
    CheckoutSessionResponse,
    CheckoutSessionStatusOut,
    PaymentItemOut,
    PaymentMethodsOut,
    PaymentOut,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def _stripe_decline_recommendations() -> list[str]:
    return [
        "Try a different payment method or card.",
        "Confirm your card has sufficient funds for online purchases.",
        "If the problem persists, contact your bank or use another card.",
    ]


def _payment_to_out(p: Payment) -> PaymentOut:
    items = []
    for pi in p.items or []:
        oi = pi.order_item
        items.append(
            PaymentItemOut(
                order_item_id=pi.order_item_id,
                movie_name=oi.movie.name if oi and oi.movie else "",
                price_at_payment=float(pi.price_at_payment),
            )
        )
    return PaymentOut(
        id=p.id,
        order_id=p.order_id,
        created_at=cast(datetime, p.created_at),
        status=p.status,
        amount=float(p.amount),
        external_payment_id=p.external_payment_id,
        items=items,
    )


@router.get("/methods", response_model=PaymentMethodsOut)
async def payment_methods_available(
    _: User = Depends(get_current_active_user),
):
    """Whether Stripe Checkout is configured (payment method availability)."""
    settings = get_settings()
    return PaymentMethodsOut(
        stripe_checkout_enabled=bool(settings.STRIPE_SECRET_KEY),
        currency=settings.STRIPE_CURRENCY.lower(),
    )


@router.post(
    "/checkout-session/{order_id}",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout_session(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create a Stripe Checkout Session for a **pending** order owned by the current user.
    Redirect the user to ``checkout_url`` to complete payment.
    """
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured (STRIPE_SECRET_KEY).",
        )

    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.user_id == current_user.id)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if order.status != OrderStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be paid.",
        )
    if not order.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has no line items.",
        )

    computed_total = sum(float(oi.price_at_order) for oi in order.items)
    if (
        order.total_amount is not None
        and abs(float(order.total_amount) - computed_total) > 0.02
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order total does not match line items; contact support.",
        )

    stripe.api_key = settings.STRIPE_SECRET_KEY

    line_items = []
    for oi in order.items:
        if oi.movie is not None and not oi.movie.available_for_purchase:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Movie «{oi.movie.name}» is no longer available for purchase; "
                    "cancel this order and update your cart."
                ),
            )
        name = (oi.movie.name if oi.movie else f"Movie #{oi.movie_id}")[:120]
        cents = int(round(float(oi.price_at_order) * 100))
        if cents < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Line item amount too small for Stripe (movie: {name}). "
                    "Minimum is usually 50 cents."
                ),
            )
        line_items.append(
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY.lower(),
                    "product_data": {"name": name},
                    "unit_amount": cents,
                },
                "quantity": 1,
            }
        )

    success_url = settings.STRIPE_SUCCESS_URL
    if "{CHECKOUT_SESSION_ID}" not in success_url:
        sep = "&" if "?" in success_url else "?"
        success_url = f"{success_url}{sep}session_id={{CHECKOUT_SESSION_ID}}"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=cast(Any, line_items),
            success_url=success_url,
            cancel_url=settings.STRIPE_CANCEL_URL,
            metadata={
                "order_id": str(order.id),
                "user_id": str(current_user.id),
            },
            client_reference_id=str(order.id),
        )
    except StripeError as e:
        msg = str(getattr(e, "user_message", None) or e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": msg,
                "recommendations": _stripe_decline_recommendations(),
            },
        ) from e

    if not session.url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe did not return a checkout URL.",
        )
    return CheckoutSessionResponse(checkout_url=session.url, session_id=session.id)


@router.get(
    "/checkout-session/{session_id}/status",
    response_model=CheckoutSessionStatusOut,
)
async def checkout_session_status(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Stripe Checkout session status after redirect; unpaid decline hints."""
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured (STRIPE_SECRET_KEY).",
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except StripeError as e:
        msg = str(getattr(e, "user_message", None) or e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": msg,
                "recommendations": _stripe_decline_recommendations(),
            },
        ) from e

    meta = getattr(sess, "metadata", None) or {}
    if meta.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout session not found",
        )

    payment_status = str(getattr(sess, "payment_status", "") or "")
    sess_status = str(getattr(sess, "status", "") or "")
    recommendations: list[str] = []
    if payment_status != "paid":
        recommendations = [
            "Complete payment on the Stripe Checkout page.",
            "If payment was declined, try another card or payment method.",
        ]
    return CheckoutSessionStatusOut(
        session_id=session_id,
        payment_status=payment_status,
        status=sess_status,
        recommendations=recommendations,
    )


@router.get("/", response_model=list[PaymentOut])
async def list_my_payments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = (
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .options(
            selectinload(Payment.items)
            .selectinload(PaymentItem.order_item)
            .selectinload(OrderItem.movie),
        )
        .order_by(Payment.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_payment_to_out(p) for p in rows]
