"""Integration tests: public movie catalog and genre listing."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.auth.security import hash_password
from src.database.models import Certification, Movie, User, UserGroup, UserGroupEnum
from src.database.session import AsyncSQLiteSessionLocal
from src.main import app


async def _seed_one_movie() -> dict[str, Any]:
    """Insert a single movie (user groups must exist from app lifespan)."""
    suf = uuid.uuid4().hex[:10]
    async with AsyncSQLiteSessionLocal() as session:
        user_g = (
            await session.execute(
                select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
            )
        ).scalar_one()

        u = User(
            email=f"catalog_{suf}@test.dev",
            hashed_password=hash_password("Secret1!"),
            is_active=True,
            group_id=user_g.id,
        )
        session.add(u)
        await session.flush()

        cert = Certification(name=f"CatalogCert-{suf}")
        session.add(cert)
        await session.flush()

        movie = Movie(
            name=f"Catalog Movie {suf}",
            year=2019,
            time=100,
            imdb=7.5,
            votes=200,
            description="catalog integration test",
            price=12.5,
            certification_id=cert.id,
        )
        session.add(movie)
        await session.commit()
        await session.refresh(movie)
        return {"movie_id": movie.id, "year": movie.year, "name": movie.name}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_list_movies_returns_200_and_json_list(client: TestClient) -> None:
    r = client.get("/movies/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_movie_404_unknown_id(client: TestClient) -> None:
    r = client.get("/movies/999999")
    assert r.status_code == 404


def test_list_genres_returns_200_and_list(client: TestClient) -> None:
    r = client.get("/genres/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_movie_detail_and_list_filters_after_seed(client: TestClient) -> None:
    data = asyncio.run(_seed_one_movie())
    mid = data["movie_id"]
    year = data["year"]

    detail = client.get(f"/movies/{mid}")
    assert detail.status_code == 200
    assert detail.json()["id"] == mid
    assert detail.json()["name"] == data["name"]

    by_year = client.get("/movies/", params={"year": year, "per_page": 20})
    assert by_year.status_code == 200
    ids = [m["id"] for m in by_year.json()]
    assert mid in ids

    sorted_desc = client.get("/movies/", params={"sort_by": "-id", "per_page": 5})
    assert sorted_desc.status_code == 200
    rows = sorted_desc.json()
    if len(rows) >= 2:
        assert rows[0]["id"] >= rows[1]["id"]
