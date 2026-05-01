"""Celery application for background tasks (token cleanup, future email)."""

from pathlib import Path

from celery import Celery

from src.config.settings import get_settings

_settings = get_settings()

_project_root = Path(__file__).resolve().parent.parent.parent
_beat_dir = _project_root / ".celery"
_beat_dir.mkdir(exist_ok=True)

app = Celery("online_cinema")
app.conf.update(
    broker_url=_settings.CELERY_BROKER_URL,
    result_backend=_settings.CELERY_RESULT_BACKEND,
    beat_schedule_filename=str(_beat_dir / "celerybeat-schedule"),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "purge-expired-auth-tokens": {
            "task": "online_cinema.purge_expired_tokens",
            "schedule": 3600.0,
        },
    },
)

from src.worker import mail_tasks  # noqa: E402, F401
from src.worker import tasks  # noqa: E402, F401
