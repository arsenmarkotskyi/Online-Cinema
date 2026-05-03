import os
import secrets
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


def _default_secret_key() -> str:
    return os.getenv("SECRET_KEY_ACCESS") or secrets.token_hex(32)


# One secret per process for tests/CI when env does not pin a key (each
# ``TestingSettings()`` would otherwise get a new ``secrets.token_hex`` and
# JWT signing in ``auth.routes`` would not match verification in ``auth.dependencies``).
_stable_testing_jwt_key: Optional[str] = None


def _stable_testing_jwt_secret() -> str:
    global _stable_testing_jwt_key
    if _stable_testing_jwt_key is None:
        _stable_testing_jwt_key = (
            os.getenv("SECRET_KEY_ACCESS")
            or os.getenv("SECRET_KEY")
            or secrets.token_hex(32)
        )
    return _stable_testing_jwt_key


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent
    PATH_TO_DB: str = str(BASE_DIR / "database" / "source" / "movies.db")
    PATH_TO_MOVIES_CSV: str = str(
        BASE_DIR / "database" / "seed_data" / "imdb_movies.csv"
    )
    DATABASE_URL: Optional[str] = None
    SECRET_KEY: str = Field(default_factory=_default_secret_key)
    # Optional: first startup creates/promotes this user to ADMIN if none
    # exists (demo/dev).
    ADMIN_BOOTSTRAP_EMAIL: Optional[str] = None
    ADMIN_BOOTSTRAP_PASSWORD: Optional[str] = None
    # If True, register/resend-activation JSON may include activation_token
    # (local dev only).
    EXPOSE_DEV_AUTH_TOKENS: bool = False
    # Stripe (payment step); leave secret empty to disable checkout creation locally.
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_SUCCESS_URL: str = "http://127.0.0.1:8000/docs"
    STRIPE_CANCEL_URL: str = "http://127.0.0.1:8000/docs"
    STRIPE_CURRENCY: str = "usd"
    # Celery (optional locally: start Redis — e.g. docker compose — then worker + beat).
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    # Public URL of this API (links in emails: activation, docs). No trailing slash.
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    # SMTP: leave SMTP_HOST empty to skip sending (Celery tasks no-op after log).
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    SMTP_USE_TLS: bool = True
    # Default when env omits it. Override ENABLE_OPENAPI_DOCS in .env
    # (e.g. false in prod).
    ENABLE_OPENAPI_DOCS: bool = True
    # If True, /docs, /redoc, and /openapi.json require an active user's JWT
    # (matches .tasks: docs visible only to authorized users).
    OPENAPI_DOCS_REQUIRE_AUTH: bool = False
    # MinIO (S3-compatible); optional until media uploads are wired to boto3/minio SDK.
    MINIO_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    MINIO_BUCKET: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        os.makedirs(Path(self.PATH_TO_DB).parent, exist_ok=True)

    def get_database_url(self) -> str:
        return self.DATABASE_URL or f"sqlite+aiosqlite:///{self.PATH_TO_DB}"

    class Config:
        env_file = ".env"
        extra = "allow"


class TestingSettings(Settings):
    PATH_TO_DB: str = ":memory:"
    SECRET_KEY: str = Field(default_factory=_stable_testing_jwt_secret)


def get_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "developing")
    if environment == "testing":
        return TestingSettings()
    return Settings()
