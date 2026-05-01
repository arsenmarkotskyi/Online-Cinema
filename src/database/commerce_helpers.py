from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Cart, Order, OrderItem, OrderStatus


async def get_or_create_cart(db: AsyncSession, user_id: int) -> Cart:
    result = await db.execute(select(Cart).where(Cart.user_id == user_id))
    cart = result.scalar_one_or_none()
    if cart is None:
        cart = Cart(user_id=user_id)
        db.add(cart)
        await db.flush()
    return cart


async def purchased_movie_ids(db: AsyncSession, user_id: int) -> set[int]:
    q = (
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user_id, Order.status == OrderStatus.PAID)
    )
    rows = (await db.execute(q)).all()
    return {r[0] for r in rows}


async def pending_order_movie_ids(db: AsyncSession, user_id: int) -> set[int]:
    q = (
        select(OrderItem.movie_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user_id, Order.status == OrderStatus.PENDING)
    )
    rows = (await db.execute(q)).all()
    return {r[0] for r in rows}
