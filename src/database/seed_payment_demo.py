"""
Seed minimal data for Stripe checkout testing: groups (via init_db),
one movie (>= $0.50), active user, cart with that movie.

Run from project root::

    python -m src.database.seed_payment_demo

Optional env (defaults shown)::

    PAYMENT_DEMO_EMAIL=stripe-demo@example.com
    PAYMENT_DEMO_PASSWORD=DemoPay1!

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from src.auth.security import hash_password
from src.database.commerce_helpers import get_or_create_cart
from src.database.models import (
    CartItem,
    Certification,
    Genre,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.database.session import AsyncSQLiteSessionLocal, init_db

DEMO_MOVIE_NAME = "Stripe Demo Movie"
DEMO_MOVIE_YEAR = 2024
DEMO_MOVIE_TIME = 90


def _demo_email() -> str:
    return os.getenv("PAYMENT_DEMO_EMAIL", "stripe-demo@example.com")


def _demo_password() -> str:
    return os.getenv("PAYMENT_DEMO_PASSWORD", "DemoPay1!")


async def seed_payment_demo() -> None:
    await init_db()

    email = _demo_email()
    password = _demo_password()

    async with AsyncSQLiteSessionLocal() as session:
        movie_result = await session.execute(
            select(Movie).where(
                Movie.name == DEMO_MOVIE_NAME,
                Movie.year == DEMO_MOVIE_YEAR,
                Movie.time == DEMO_MOVIE_TIME,
            )
        )
        movie: Movie | None = movie_result.scalar_one_or_none()

        if movie is None:
            cert_result = await session.execute(
                select(Certification).where(Certification.name == "PG-13")
            )
            cert = cert_result.scalar_one_or_none()
            if cert is None:
                cert = Certification(name="PG-13")
                session.add(cert)
                await session.flush()

            genre_result = await session.execute(
                select(Genre).where(Genre.name == "Demo")
            )
            genre = genre_result.scalar_one_or_none()
            if genre is None:
                genre = Genre(name="Demo")
                session.add(genre)
                await session.flush()

            movie = Movie(
                name=DEMO_MOVIE_NAME,
                year=DEMO_MOVIE_YEAR,
                time=DEMO_MOVIE_TIME,
                imdb=8.0,
                votes=1000,
                meta_score=80.0,
                gross=1.0,
                description="Seed movie for Stripe payment testing.",
                price=9.99,
                certification_id=cert.id,
                genres=[genre],
            )
            session.add(movie)
            await session.flush()

        assert movie is not None

        user_group_result = await session.execute(
            select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
        )
        user_group = user_group_result.scalar_one()

        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
                group_id=user_group.id,
            )
            session.add(user)
            await session.flush()
        else:
            user.is_active = True
            if user.group_id is None:
                user.group_id = user_group.id

        cart = await get_or_create_cart(session, user.id)
        result = await session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart.id,
                CartItem.movie_id == movie.id,
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(CartItem(cart_id=cart.id, movie_id=movie.id))

        await session.commit()

        mid = movie.id
        uid = user.id

    print("Payment demo seed OK.")
    print(f"  Login: POST /auth/login  email={email!r}  password={password!r}")
    print(
        f"  user_id={uid}, movie_id={mid}, cart has this movie → "
        "POST /orders/ then checkout."
    )


if __name__ == "__main__":
    asyncio.run(seed_payment_demo())
