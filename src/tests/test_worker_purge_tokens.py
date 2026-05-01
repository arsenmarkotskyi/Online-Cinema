"""Tests for Celery task ``purge_expired_tokens`` (sync SQLite file)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    ActivationToken,
    Base,
    PasswordResetToken,
    RefreshToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.worker.tasks import purge_expired_tokens


def _build_token_db(db_path: str) -> None:
    """Create schema and rows: expired vs valid tokens across three tables."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=1)

    with Session() as session:
        group = UserGroup(name=UserGroupEnum.USER)
        session.add(group)
        session.flush()

        def add_user(suffix: str) -> User:
            u = User(
                email=f"purge_{suffix}_{uuid.uuid4().hex[:8]}@test.dev",
                hashed_password="hashed",
                is_active=True,
                group_id=group.id,
            )
            session.add(u)
            session.flush()
            return u

        u_act_exp = add_user("act_exp")
        u_act_ok = add_user("act_ok")
        u_pwd_exp = add_user("pwd_exp")
        u_pwd_ok = add_user("pwd_ok")
        u_refresh = add_user("ref")

        session.add(
            ActivationToken(
                user_id=u_act_exp.id, token="tok_act_expired", expires_at=past
            )
        )
        session.add(
            ActivationToken(
                user_id=u_act_ok.id, token="tok_act_valid", expires_at=future
            )
        )
        session.add(
            PasswordResetToken(
                user_id=u_pwd_exp.id, token="tok_pwd_expired", expires_at=past
            )
        )
        session.add(
            PasswordResetToken(
                user_id=u_pwd_ok.id, token="tok_pwd_valid", expires_at=future
            )
        )
        session.add(
            RefreshToken(
                user_id=u_refresh.id,
                token="tok_refresh_expired",
                expires_at=past,
            )
        )
        session.add(
            RefreshToken(
                user_id=u_refresh.id,
                token="tok_refresh_valid",
                expires_at=future,
            )
        )
        session.commit()
    engine.dispose()


def test_purge_expired_tokens_removes_only_expired(tmp_path) -> None:
    db_path = str(tmp_path / "purge_tokens.db")
    _build_token_db(db_path)
    settings = SimpleNamespace(PATH_TO_DB=db_path)

    with patch("src.worker.tasks.get_settings", return_value=settings):
        removed = purge_expired_tokens()

    assert removed == 3

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as session:
        n_act = session.scalar(select(func.count()).select_from(ActivationToken))
        n_pwd = session.scalar(select(func.count()).select_from(PasswordResetToken))
        n_ref = session.scalar(select(func.count()).select_from(RefreshToken))
    engine.dispose()

    assert n_act == 1
    assert n_pwd == 1
    assert n_ref == 1


def test_purge_expired_tokens_no_tables_returns_zero(tmp_path) -> None:
    """Empty SQLite file: OperationalError is swallowed; task returns 0."""
    db_path = str(tmp_path / "empty.db")
    open(db_path, "wb").close()
    settings = SimpleNamespace(PATH_TO_DB=db_path)

    with patch("src.worker.tasks.get_settings", return_value=settings):
        removed = purge_expired_tokens()

    assert removed == 0


def test_purge_expired_tokens_rejects_memory_db() -> None:
    settings = SimpleNamespace(PATH_TO_DB=":memory:")
    with (
        patch("src.worker.tasks.get_settings", return_value=settings),
        pytest.raises(RuntimeError, match="file-based"),
    ):
        purge_expired_tokens()
