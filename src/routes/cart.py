from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import get_current_active_user
from src.database.commerce_helpers import get_or_create_cart, purchased_movie_ids
from src.database.models import CartItem, Movie, User
from src.database.session import get_db
from src.schemas.cart import CartItemOut, CartOut

router = APIRouter(prefix="/cart", tags=["cart"])


def _genre_names(movie: Movie) -> list[str]:
    return [g.name for g in (movie.genres or [])]


@router.get("/", response_model=CartOut)
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cart = await get_or_create_cart(db, current_user.id)
    stmt = (
        select(CartItem)
        .where(CartItem.cart_id == cart.id)
        .options(selectinload(CartItem.movie).selectinload(Movie.genres))
        .order_by(CartItem.added_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    items_out: list[CartItemOut] = []
    subtotal = 0.0
    for row in rows:
        m = row.movie
        if m is None:
            continue
        price = float(m.price)
        subtotal += price
        items_out.append(
            CartItemOut(
                movie_id=m.id,
                name=m.name,
                year=m.year,
                price=price,
                genres=_genre_names(m),
                added_at=cast(datetime | None, row.added_at),
            )
        )
    return CartOut(items=items_out, subtotal=subtotal)


@router.post("/items/{movie_id}", status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    movie = await db.get(Movie, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found"
        )

    owned = await purchased_movie_ids(db, current_user.id)
    if movie_id in owned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This movie is already purchased; repeat purchase is not allowed.",
        )

    cart = await get_or_create_cart(db, current_user.id)
    existing = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.movie_id == movie_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This movie is already in your cart.",
        )

    db.add(CartItem(cart_id=cart.id, movie_id=movie_id))
    await db.commit()
    return {"detail": "Movie added to cart"}


@router.delete("/items/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_cart(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cart = await get_or_create_cart(db, current_user.id)
    result = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.movie_id == movie_id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not in cart"
        )
    await db.delete(item)
    await db.commit()
    return


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cart = await get_or_create_cart(db, current_user.id)
    result = await db.execute(select(CartItem).where(CartItem.cart_id == cart.id))
    for row in result.scalars().all():
        await db.delete(row)
    await db.commit()
    return
