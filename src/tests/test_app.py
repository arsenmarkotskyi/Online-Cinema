"""Smoke tests for the FastAPI app (ENVIRONMENT=testing from conftest)."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_bootstrap_info_ok(client: TestClient):
    r = client.get("/admin/bootstrap-info")
    assert r.status_code == 200
    data = r.json()
    assert "bootstrap_configured" in data
    assert "admin_exists" in data


def test_docs_available_when_enabled(client: TestClient):
    r = client.get("/docs")
    assert r.status_code in (200, 307)
