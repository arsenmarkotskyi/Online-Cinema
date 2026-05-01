"""Must-have: protected routes return 401 without Authorization (no DB seed)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_get_routes_require_auth(client: TestClient) -> None:
    for path in (
        "/cart/",
        "/orders/",
        "/profile/",
        "/payments/",
        "/payments/methods",
        "/favorites/",
        "/notifications/",
    ):
        assert client.get(path).status_code == 401, path


def test_mutating_routes_require_auth(client: TestClient) -> None:
    assert client.post("/cart/items/1").status_code == 401
    assert client.delete("/cart/items/1").status_code == 401
    assert client.delete("/cart/").status_code == 401
    assert client.post("/orders/").status_code == 401
    assert client.post("/payments/checkout-session/1").status_code == 401
