"""OpenAPI UI: public vs JWT-protected (OPENAPI_DOCS_REQUIRE_AUTH)."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.dependencies import get_current_active_user
from src.main import create_app


def test_public_docs_reach_openapi_json(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("ENABLE_OPENAPI_DOCS", "true")
    monkeypatch.setenv("OPENAPI_DOCS_REQUIRE_AUTH", "false")
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200


def test_protected_docs_require_bearer(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("ENABLE_OPENAPI_DOCS", "true")
    monkeypatch.setenv("OPENAPI_DOCS_REQUIRE_AUTH", "true")
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 401
        assert client.get("/redoc").status_code == 401
        assert client.get("/openapi.json").status_code == 401


def test_protected_docs_ok_with_dependency_override(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("ENABLE_OPENAPI_DOCS", "true")
    monkeypatch.setenv("OPENAPI_DOCS_REQUIRE_AUTH", "true")
    app = create_app()

    async def _fake_user() -> MagicMock:
        u = MagicMock()
        u.is_active = True
        return u

    app.dependency_overrides[get_current_active_user] = _fake_user
    try:
        with TestClient(app) as client:
            r_docs = client.get("/docs")
            r_redoc = client.get("/redoc")
            r_openapi = client.get("/openapi.json")
    finally:
        app.dependency_overrides.clear()

    assert r_docs.status_code == 200
    assert "swagger" in r_docs.text.lower()
    assert r_redoc.status_code == 200
    assert r_openapi.status_code == 200
    assert "openapi" in r_openapi.json()
