from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from stripe import StripeError

from src.auth.dependencies import get_current_active_user
from src.config.settings import get_settings
from src.database.commerce_helpers import (
    get_or_create_cart,
    pending_order_movie_ids,
    purchased_movie_ids,
)
from src.database.models import (
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    User,
)
from src.database.session import get_db
from src.schemas.orders import OrderCreateResult, OrderItemOut, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


def _order_to_out(order: Order) -> OrderOut:
    items = [
        OrderItemOut(
            movie_id=oi.movie_id,
            movie_name=oi.movie.name if oi.movie else "",
            price_at_order=float(oi.price_at_order),
        )
        for oi in (order.items or [])
    ]
    return OrderOut(
        id=order.id,
        created_at=cast(datetime, order.created_at),
        status=order.status,
        total_amount=(
            float(order.total_amount) if order.total_amount is not None else None
        ),
        items=items,
    )


@router.post("/", response_model=OrderCreateResult, status_code=status.HTTP_201_CREATED)
async def create_order_from_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cart = await get_or_create_cart(db, current_user.id)
    stmt = (
        select(CartItem)
        .where(CartItem.cart_id == cart.id)
        .options(selectinload(CartItem.movie))
    )
    cart_rows = (await db.execute(stmt)).scalars().all()
    if not cart_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty; add movies before placing an order.",
        )

    purchased = await purchased_movie_ids(db, current_user.id)
    pending_movies = await pending_order_movie_ids(db, current_user.id)

    eligible: list[CartItem] = []
    excluded_purchased: list[int] = []
    excluded_pending: list[int] = []
    messages: list[str] = []

    for ci in cart_rows:
        mid = ci.movie_id
        if ci.movie is None:
            messages.append(
                f"Movie id {mid} is no longer available and was removed from cart."
            )
            await db.delete(ci)
            continue
        if not ci.movie.available_for_purchase:
            messages.append(
                f"Movie id {mid} is not available for purchase "
                "(withdrawn or region-locked) and was excluded from this order."
            )
            await db.delete(ci)
            continue
        if mid in purchased:
            excluded_purchased.append(mid)
            messages.append(
                f"Movie id {mid} is already purchased and was removed from this order."
            )
            continue
        if mid in pending_movies:
            excluded_pending.append(mid)
            messages.append(
                f"Movie id {mid} is already in a pending order; "
                "finish or cancel it first."
            )
            continue
        eligible.append(ci)

    if not eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "No items can be ordered",
                "excluded_already_purchased": excluded_purchased,
                "excluded_pending_order": excluded_pending,
                "messages": messages,
            },
        )

    total = Decimal("0")
    order = Order(user_id=current_user.id, status=OrderStatus.PENDING)
    db.add(order)
    await db.flush()

    for ci in eligible:
        m = ci.movie
        assert m is not None
        price = Decimal(str(m.price))
        total += price
        db.add(
            OrderItem(
                order_id=order.id,
                movie_id=m.id,
                price_at_order=float(price),
            )
        )

    order.total_amount = float(total)

    eligible_ids = {ci.movie_id for ci in eligible}
    for ci in cart_rows:
        if ci.movie_id in eligible_ids or ci.movie_id in excluded_purchased:
            await db.delete(ci)

    await db.commit()

    order_stmt = (
        select(Order)
        .where(Order.id == order.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.movie),
        )
    )
    fresh = (await db.execute(order_stmt)).scalar_one()
    return OrderCreateResult(
        order=_order_to_out(fresh),
        excluded_already_purchased=excluded_purchased,
        excluded_pending_order=excluded_pending,
        messages=messages,
    )


@router.get("/", response_model=list[OrderOut])
async def list_my_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
        .order_by(Order.created_at.desc())
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [_order_to_out(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
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
    return _order_to_out(order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
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
            detail=(
                "Only pending orders can be canceled this way; "
                "paid orders require a refund flow."
            ),
        )
    order.status = OrderStatus.CANCELED
    await db.commit()
    await db.refresh(order)
    stmt = (
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
    )
    fresh = (await db.execute(stmt)).scalar_one()
    return _order_to_out(fresh)


def _checkout_payment_intent_id(session: Any) -> str | None:
    """Resolve PaymentIntent id from a Checkout Session (Stripe object or dict-like)."""
    pi = getattr(session, "payment_intent", None)
    if pi is None:
        try:
            pi = session["payment_intent"]
        except (KeyError, TypeError):
            pi = None
    if pi is None:
        return None
    if isinstance(pi, str):
        return pi
    if hasattr(pi, "id"):
        return str(pi.id)
    if isinstance(pi, dict):
        return str(pi.get("id") or "")
    return None


@router.post("/{order_id}/refund", response_model=OrderOut)
async def refund_paid_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Full refund for a **paid** order via Stripe (Checkout Session → PaymentIntent).

    After Stripe confirms the refund, the order becomes ``refunded`` and the
    linked payment ``refunded``. Idempotent if already refunded locally.
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

    if order.status == OrderStatus.REFUNDED:
        return _order_to_out(order)

    if order.status != OrderStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only paid orders can be refunded.",
        )

    pay_stmt = (
        select(Payment)
        .where(
            Payment.order_id == order_id,
            Payment.user_id == current_user.id,
            Payment.status == PaymentStatus.SUCCESSFUL,
        )
        .order_by(Payment.id.desc())
        .limit(1)
    )
    payment = (await db.execute(pay_stmt)).scalar_one_or_none()
    if not payment or not payment.external_payment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No successful Stripe payment found for this order.",
        )

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        checkout_session = stripe.checkout.Session.retrieve(
            payment.external_payment_id,
            expand=["payment_intent"],
        )
        pi_id = _checkout_payment_intent_id(checkout_session)
        if not pi_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Checkout session has no payment intent; cannot refund.",
            )
        try:
            stripe.Refund.create(payment_intent=pi_id)
        except StripeError as ire:
            err = str(ire).lower()
            if "already been refunded" not in err and "already refunded" not in err:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(getattr(ire, "user_message", None) or ire),
                ) from ire
    except HTTPException:
        raise
    except StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(getattr(e, "user_message", None) or e),
        ) from e

    payment.status = PaymentStatus.REFUNDED
    order.status = OrderStatus.REFUNDED
    await db.commit()
    await db.refresh(order, attribute_names=["status"])
    await db.refresh(payment, attribute_names=["status"])

    stmt = (
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items).selectinload(OrderItem.movie))
    )
    fresh = (await db.execute(stmt)).scalar_one()
    return _order_to_out(fresh)
