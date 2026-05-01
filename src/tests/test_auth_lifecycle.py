"""Integration tests: register → activate from DB → login (Celery email mocked)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.database.models import ActivationToken, User
from src.database.session import AsyncSQLiteSessionLocal
from src.main import app


async def _activation_token_for_email(email: str) -> str:
    async with AsyncSQLiteSessionLocal() as session:
        ur = await session.execute(select(User).where(User.email == email))
        user = ur.scalar_one()
        tr = await session.execute(
            select(ActivationToken).where(ActivationToken.user_id == user.id)
        )
        at = tr.scalar_one()
        return at.token


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_register_activate_login_flow(client: TestClient, monkeypatch) -> None:
    mock_send = MagicMock()
    monkeypatch.setattr(
        "src.worker.mail_tasks.send_activation_email",
        mock_send,
    )

    email = f"life_{uuid.uuid4().hex[:12]}@test.dev"
    password = "GoodPass1!"

    reg = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text
    mock_send.delay.assert_called_once()

    token = asyncio.run(_activation_token_for_email(email))
    act = client.post(f"/auth/activate/{token}")
    assert act.status_code == 200, act.text

    login = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert "access_token" in body and "refresh_token" in body

    refresh = body["refresh_token"]
    out = client.post("/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 200

    bad_refresh = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert bad_refresh.status_code == 401


def test_activate_invalid_token_404(client: TestClient) -> None:
    r = client.post("/auth/activate/not-a-real-token-ever")
    assert r.status_code == 404
