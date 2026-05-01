"""Tests for POST /orders/{id}/refund (Stripe full refund)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.auth.security import hash_password
from src.database.models import (
    Certification,
    Movie,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.database.session import AsyncSQLiteSessionLocal
from src.main import app


async def _seed_paid_order() -> dict[str, Any]:
    suf = uuid.uuid4().hex[:10]
    async with AsyncSQLiteSessionLocal() as session:
        user_g = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
            )
        ).scalar_one()

        user = User(
            email=f"buyer_ref_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=user_g.id,
        )
        session.add(user)
        await session.flush()

        cert = Certification(name=f"Cref-{suf}")
        session.add(cert)
        await session.flush()

        movie = Movie(
            name=f"Refund Movie {suf}",
            year=2022,
            time=95,
            imdb=7.5,
            votes=200,
            description="d",
            price=10.00,
            certification_id=cert.id,
        )
        session.add(movie)
        await session.flush()

        order = Order(
            user_id=user.id,
            status=OrderStatus.PAID,
            total_amount=10.00,
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                movie_id=movie.id,
                price_at_order=10.00,
            )
        )
        session.add(
            Payment(
                user_id=user.id,
                order_id=order.id,
                status=PaymentStatus.SUCCESSFUL,
                amount=10.00,
                external_payment_id=f"cs_test_{suf}",
            )
        )
        await session.commit()

        return {
            "email": user.email,
            "password": "Secret1!",
            "order_id": order.id,
        }


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


def test_refund_rejects_pending_order(client: TestClient) -> None:
    """No Stripe call: pending orders cannot use refund endpoint."""
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
    suf = uuid.uuid4().hex[:8]

    async def _seed_pending() -> dict[str, Any]:
        async with AsyncSQLiteSessionLocal() as session:
            user_g = (
                await session.execute(
                    select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
                )
            ).scalar_one()
            user = User(
                email=f"pend_{suf}@t.dev",
                hashed_password=hash_password("Secret1!"),
                is_active=True,
                group_id=user_g.id,
            )
            session.add(user)
            await session.flush()
            cert = Certification(name=f"cp-{suf}")
            session.add(cert)
            await session.flush()
            movie = Movie(
                name=f"Mpend {suf}",
                year=2023,
                time=90,
                imdb=6.0,
                votes=1,
                description="d",
                price=5.0,
                certification_id=cert.id,
            )
            session.add(movie)
            await session.flush()
            order = Order(
                user_id=user.id,
                status=OrderStatus.PENDING,
                total_amount=5.0,
            )
            session.add(order)
            await session.flush()
            session.add(
                OrderItem(
                    order_id=order.id,
                    movie_id=movie.id,
                    price_at_order=5.0,
                )
            )
            await session.commit()
            return {"email": user.email, "order_id": order.id}

    data = asyncio.run(_seed_pending())
    token = _login(client, data["email"], "Secret1!")
    r = client.post(
        f"/orders/{data['order_id']}/refund",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "paid" in r.json()["detail"].lower()


def test_refund_paid_order_updates_status(client: TestClient) -> None:
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
    data = asyncio.run(_seed_paid_order())
    token = _login(client, data["email"], data["password"])
    oid = data["order_id"]

    fake_session = SimpleNamespace(payment_intent="pi_test_fake")

    with (
        patch(
            "src.routes.orders.stripe.checkout.Session.retrieve",
            return_value=fake_session,
        ) as m_ret,
        patch("src.routes.orders.stripe.Refund.create") as m_ref,
    ):
        m_ref.return_value = SimpleNamespace(id="re_test")
        r = client.post(
            f"/orders/{oid}/refund",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "refunded"
    m_ret.assert_called_once()
    m_ref.assert_called_once_with(payment_intent="pi_test_fake")

    r2 = client.post(
        f"/orders/{oid}/refund",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "refunded"


def test_refund_503_without_stripe_key(client: TestClient) -> None:
    """Empty env must win over .env; otherwise Stripe runs and returns 502."""
    old = os.environ.get("STRIPE_SECRET_KEY")
    os.environ["STRIPE_SECRET_KEY"] = ""
    try:
        data = asyncio.run(_seed_paid_order())
        token = _login(client, data["email"], data["password"])
        r = client.post(
            f"/orders/{data['order_id']}/refund",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 503
    finally:
        if old is not None:
            os.environ["STRIPE_SECRET_KEY"] = old
        else:
            os.environ.pop("STRIPE_SECRET_KEY", None)
