"""Celery tasks (sync DB access; API uses async SQLAlchemy separately)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy import create_engine, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from src.config.settings import get_settings
from src.database.models import (
    ActivationToken,
    PasswordResetToken,
    RefreshToken,
    RevokedAccessToken,
)
from src.worker.celery_app import app

logger = logging.getLogger(__name__)


def _sync_sqlite_url() -> str:
    settings = get_settings()
    raw = settings.PATH_TO_DB
    if isinstance(raw, str) and ":memory:" in raw:
        raise RuntimeError("Celery DB tasks require a file-based SQLite PATH_TO_DB.")
    path = Path(str(raw)).expanduser().resolve()
    return f"sqlite:///{path}"


@app.task(name="online_cinema.purge_expired_tokens")
def purge_expired_tokens() -> int:
    """
    Remove expired activation, password-reset, refresh, and revoked-access rows.

    Scheduled by Celery Beat (hourly). Matches ``.tasks`` requirement to purge
    expired activation tokens periodically.
    """
    engine = create_engine(_sync_sqlite_url(), pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    removed = 0
    try:
        with session_factory() as session:
            for model in (
                ActivationToken,
                PasswordResetToken,
                RefreshToken,
                RevokedAccessToken,
            ):
                res = session.execute(delete(model).where(model.expires_at < now))
                cr = cast(CursorResult[Any], res)
                removed += cr.rowcount or 0
            session.commit()
    except OperationalError as exc:
        if "no such table" in str(exc).lower():
            logger.warning(
                "purge_expired_tokens skipped: tables missing; "
                "start FastAPI once to run init_db."
            )
            return 0
        raise
    finally:
        engine.dispose()
    return removed
