from datetime import datetime
from typing import Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_admin, require_moderator
from src.database.models import (
    ActivationToken,
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentItem,
    PaymentStatus,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.database.session import get_db
from src.routes.orders import _order_to_out
from src.routes.payments import _payment_to_out
from src.schemas.admin import AdminBootstrapInfo, GroupOut, UserAdminOut, UserGroupPatch
from src.schemas.admin_commerce import (
    AdminCartItemOut,
    AdminCartOut,
    AdminOrderOut,
    AdminPaymentOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_admin_out(user: User) -> UserAdminOut:
    role = user.group.name if user.group else None
    return UserAdminOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        group=role,
    )


@router.get("/bootstrap-info", response_model=AdminBootstrapInfo)
async def bootstrap_info(db: AsyncSession = Depends(get_db)):
    """Public: whether bootstrap env is set and if any admin exists (no secrets)."""
    from src.config.settings import get_settings

    settings = get_settings()
    configured = bool(
        settings.ADMIN_BOOTSTRAP_EMAIL and settings.ADMIN_BOOTSTRAP_PASSWORD
    )
    result = await db.execute(
        select(User.id)
        .join(UserGroup, User.group_id == UserGroup.id)
        .where(UserGroup.name == UserGroupEnum.ADMIN)
        .limit(1)
    )
    admin_exists = result.scalar_one_or_none() is not None
    return AdminBootstrapInfo(
        bootstrap_configured=configured,
        admin_exists=admin_exists,
    )


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(UserGroup).order_by(UserGroup.id))
    return list(result.scalars().all())


@router.patch("/users/{user_id}/group", response_model=UserAdminOut)
async def set_user_group(
    user_id: int,
    body: UserGroupPatch,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use another admin account to change your own group.",
        )
    stmt = select(User).options(selectinload(User.group)).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    g = await db.execute(select(UserGroup).where(UserGroup.name == body.group))
    group = g.scalar_one_or_none()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown group"
        )

    user.group_id = group.id
    await db.commit()
    await db.refresh(user, attribute_names=["group"])
    return _user_admin_out(user)


@router.post("/users/{user_id}/activate", response_model=UserAdminOut)
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    stmt = select(User).options(selectinload(User.group)).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.is_active = True
    tok_result = await db.execute(
        select(ActivationToken).where(ActivationToken.user_id == user_id)
    )
    old = tok_result.scalar_one_or_none()
    if old:
        await db.delete(old)
    await db.commit()
    await db.refresh(user, attribute_names=["group"])
    return _user_admin_out(user)


@router.get("/orders", response_model=list[AdminOrderOut])
async def admin_list_orders(
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
    user_id: Optional[int] = Query(None, description="Filter by buyer user id"),
    status: Optional[OrderStatus] = Query(None, description="Filter by order status"),
    created_from: Optional[datetime] = Query(
        None, description="ISO datetime, inclusive"
    ),
    created_to: Optional[datetime] = Query(None, description="ISO datetime, inclusive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all orders with optional filters (moderator or admin)."""
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.movie),
            selectinload(Order.user),
        )
        .order_by(Order.created_at.desc())
    )
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if created_from is not None:
        stmt = stmt.where(Order.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Order.created_at <= created_to)
    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    out: list[AdminOrderOut] = []
    for order in rows:
        base = _order_to_out(order)
        out.append(
            AdminOrderOut(
                id=base.id,
                user_id=order.user_id,
                user_email=order.user.email if order.user else "",
                created_at=base.created_at,
                status=base.status,
                total_amount=base.total_amount,
                items=base.items,
            )
        )
    return out


@router.get("/carts", response_model=list[AdminCartOut])
async def admin_list_carts(
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
    user_id: Optional[int] = Query(None, description="Filter by cart owner user id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List user carts with line items (moderator or admin)."""
    stmt = (
        select(Cart)
        .options(
            selectinload(Cart.user),
            selectinload(Cart.items).selectinload(CartItem.movie),
        )
        .order_by(Cart.id.asc())
    )
    if user_id is not None:
        stmt = stmt.where(Cart.user_id == user_id)
    stmt = stmt.offset(offset).limit(limit)
    carts = (await db.execute(stmt)).scalars().all()
    out: list[AdminCartOut] = []
    for cart in carts:
        items_out: list[AdminCartItemOut] = []
        subtotal = 0.0
        for row in cart.items or []:
            m = row.movie
            if m is None:
                continue
            price = float(m.price)
            subtotal += price
            items_out.append(
                AdminCartItemOut(
                    movie_id=m.id,
                    name=m.name,
                    year=m.year,
                    price=price,
                    added_at=cast(datetime | None, row.added_at),
                )
            )
        email = cart.user.email if cart.user else ""
        out.append(
            AdminCartOut(
                user_id=cart.user_id,
                user_email=email,
                item_count=len(items_out),
                subtotal=subtotal,
                items=items_out,
            )
        )
    return out


@router.get("/payments", response_model=list[AdminPaymentOut])
async def admin_list_payments(
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
    user_id: Optional[int] = Query(None, description="Filter by payer user id"),
    status: Optional[PaymentStatus] = Query(
        None, description="Filter by payment status"
    ),
    created_from: Optional[datetime] = Query(
        None, description="ISO datetime, inclusive"
    ),
    created_to: Optional[datetime] = Query(None, description="ISO datetime, inclusive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all payments with optional filters."""
    stmt = (
        select(Payment)
        .options(
            selectinload(Payment.user),
            selectinload(Payment.items)
            .selectinload(PaymentItem.order_item)
            .selectinload(OrderItem.movie),
        )
        .order_by(Payment.created_at.desc())
    )
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    if created_from is not None:
        stmt = stmt.where(Payment.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Payment.created_at <= created_to)
    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    result: list[AdminPaymentOut] = []
    for p in rows:
        base = _payment_to_out(p)
        result.append(
            AdminPaymentOut(
                id=base.id,
                user_id=p.user_id,
                user_email=p.user.email if p.user else "",
                order_id=base.order_id,
                created_at=base.created_at,
                status=base.status,
                amount=base.amount,
                external_payment_id=base.external_payment_id,
                items=base.items,
            )
        )
    return result
