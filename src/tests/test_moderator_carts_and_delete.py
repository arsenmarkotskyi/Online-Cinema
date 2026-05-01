"""Tests: GET /admin/carts, DELETE /movies when movie is in carts, notifications."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.auth.security import hash_password
from src.database.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.database.session import AsyncSQLiteSessionLocal
from src.main import app


async def _seed_moderator_buyer_movie_in_cart() -> dict[str, Any]:
    """Create moderator, buyer, certification, movie, cart line (unique emails)."""
    suf = uuid.uuid4().hex[:10]
    async with AsyncSQLiteSessionLocal() as session:
        mod_g = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.MODERATOR)
            )
        ).scalar_one()
        user_g = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
            )
        ).scalar_one()

        buyer = User(
            email=f"buyer_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=user_g.id,
        )
        mod = User(
            email=f"mod_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=mod_g.id,
        )
        session.add_all([buyer, mod])
        await session.flush()

        cert = Certification(name=f"Cert-{suf}")
        session.add(cert)
        await session.flush()

        movie = Movie(
            name=f"Cart Block {suf}",
            year=2020,
            time=90,
            imdb=7.0,
            votes=100,
            description="test",
            price=9.99,
            certification_id=cert.id,
        )
        session.add(movie)
        await session.flush()

        cart = Cart(user_id=buyer.id)
        session.add(cart)
        await session.flush()
        session.add(CartItem(cart_id=cart.id, movie_id=movie.id))
        await session.commit()

        return {
            "buyer_email": buyer.email,
            "mod_email": mod.email,
            "movie_id": movie.id,
            "password": "Secret1!",
        }


async def _seed_movie_only_no_cart() -> dict[str, Any]:
    """Moderator + movie not in any cart (for successful delete)."""
    suf = uuid.uuid4().hex[:10]
    async with AsyncSQLiteSessionLocal() as session:
        mod_g = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.MODERATOR)
            )
        ).scalar_one()

        mod = User(
            email=f"modonly_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=mod_g.id,
        )
        session.add(mod)
        await session.flush()

        cert = Certification(name=f"CertD-{suf}")
        session.add(cert)
        await session.flush()

        movie = Movie(
            name=f"Deletable {suf}",
            year=2021,
            time=91,
            imdb=8.0,
            votes=50,
            description="test",
            price=4.99,
            certification_id=cert.id,
        )
        session.add(movie)
        await session.commit()

        return {"mod_email": mod.email, "movie_id": movie.id, "password": "Secret1!"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_admin_carts_401_without_token(client: TestClient) -> None:
    r = client.get("/admin/carts")
    assert r.status_code == 401


def test_admin_carts_403_as_regular_user(client: TestClient) -> None:
    data = asyncio.run(_seed_moderator_buyer_movie_in_cart())
    token = _login(client, data["buyer_email"], data["password"])
    r = client.get("/admin/carts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_carts_200_lists_cart_with_items(client: TestClient) -> None:
    data = asyncio.run(_seed_moderator_buyer_movie_in_cart())
    token = _login(client, data["mod_email"], data["password"])
    r = client.get("/admin/carts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert any(
        row.get("user_email") == data["buyer_email"] and row.get("item_count", 0) >= 1
        for row in rows
    )


def test_delete_movie_409_in_cart_notifies_moderators(client: TestClient) -> None:
    data = asyncio.run(_seed_moderator_buyer_movie_in_cart())
    mod_token = _login(client, data["mod_email"], data["password"])
    mid = data["movie_id"]

    r = client.delete(
        f"/movies/{mid}",
        headers={"Authorization": f"Bearer {mod_token}"},
    )
    assert r.status_code == 409
    assert "carts" in r.json()["detail"].lower()
    assert "notified" in r.json()["detail"].lower()

    n = client.get("/notifications", headers={"Authorization": f"Bearer {mod_token}"})
    assert n.status_code == 200
    messages = [x.get("message", "") for x in n.json()]
    assert any("Delete attempt blocked" in m for m in messages)
    assert any(str(mid) in m for m in messages)


def test_delete_movie_204_when_not_in_cart(client: TestClient) -> None:
    data = asyncio.run(_seed_movie_only_no_cart())
    mod_token = _login(client, data["mod_email"], data["password"])
    mid = data["movie_id"]

    r = client.delete(
        f"/movies/{mid}",
        headers={"Authorization": f"Bearer {mod_token}"},
    )
    assert r.status_code == 204
