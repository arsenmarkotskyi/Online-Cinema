"""Password complexity on register (Pydantic validators in ``schemas.auth``)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_register_rejects_short_password(client: TestClient) -> None:
    r = client.post(
        "/auth/register",
        json={"email": f"u_{uuid.uuid4().hex[:12]}@test.dev", "password": "Aa1!abc"},
    )
    assert r.status_code == 422
    assert "8" in str(r.json()).lower()


def test_register_rejects_password_without_uppercase(client: TestClient) -> None:
    r = client.post(
        "/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:12]}@test.dev",
            "password": "lowercase1!",
        },
    )
    assert r.status_code == 422


def test_register_rejects_password_without_special_char(client: TestClient) -> None:
    r = client.post(
        "/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:12]}@test.dev",
            "password": "NoSpecial1",
        },
    )
    assert r.status_code == 422
