"""Tests for GET /payments/methods and checkout session status."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.auth.security import hash_password
from src.database.models import User, UserGroup, UserGroupEnum
from src.database.session import AsyncSQLiteSessionLocal
from src.main import app


async def _seed_active_user() -> dict[str, str | int]:
    suf = uuid.uuid4().hex[:10]
    async with AsyncSQLiteSessionLocal() as session:
        ug = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
            )
        ).scalar_one()
        u = User(
            email=f"payments_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=ug.id,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return {"email": u.email, "user_id": u.id}


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


def test_payment_methods_authenticated(client: TestClient) -> None:
    data = asyncio.run(_seed_active_user())
    token = _login(client, str(data["email"]), "Secret1!")
    r = client.get(
        "/payments/methods",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "stripe_checkout_enabled" in body
    assert "currency" in body
    assert isinstance(body["stripe_checkout_enabled"], bool)


def test_checkout_session_status_ok_for_owner(client: TestClient) -> None:
    data = asyncio.run(_seed_active_user())
    token = _login(client, str(data["email"]), "Secret1!")
    uid = data["user_id"]
    fake = SimpleNamespace(
        metadata={"user_id": str(uid)},
        payment_status="unpaid",
        status="open",
    )
    with (
        patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake"}),
        patch(
            "src.routes.payments.stripe.checkout.Session.retrieve",
            return_value=fake,
        ),
    ):
        r = client.get(
            "/payments/checkout-session/cs_test_xyz/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["session_id"] == "cs_test_xyz"
    assert out["payment_status"] == "unpaid"
    assert len(out["recommendations"]) >= 1


def test_checkout_session_status_404_other_user_metadata(client: TestClient) -> None:
    data = asyncio.run(_seed_active_user())
    token = _login(client, str(data["email"]), "Secret1!")
    fake = SimpleNamespace(
        metadata={"user_id": str(uuid.uuid4())},
        payment_status="unpaid",
        status="open",
    )
    with (
        patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake"}),
        patch(
            "src.routes.payments.stripe.checkout.Session.retrieve",
            return_value=fake,
        ),
    ):
        r = client.get(
            "/payments/checkout-session/cs_foreign/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404
