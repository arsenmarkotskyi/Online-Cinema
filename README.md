# Online Cinema

REST API for an online cinema: movie catalog, accounts with email activation, favorites, cart, orders, **Stripe Checkout** payments, webhooks, and roles (user / moderator / admin). Functional requirements are described in [`.tasks`](.tasks).

## Stack

- **Python 3.12**, **FastAPI**, **SQLAlchemy 2** (async), **SQLite** via `aiosqlite`
- **JWT** (access + refresh, access revocation on logout via `jti` denylist)
- **Celery** + **Redis** (email tasks, periodic token cleanup)
- **Stripe** for payments; optional **MinIO** (S3-compatible) in Docker Compose

## Prerequisites

- [Poetry](https://python-poetry.org/) 1.8+ (see `pyproject.toml` and `poetry.lock`)
- **Docker** and **Docker Compose** for the full local stack

## Local development

```bash
cd online-cinema
poetry install --with dev
cp .env.example .env
# Edit .env for Stripe, SMTP, Redis, etc.
poetry run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

- API base URL: `http://127.0.0.1:8000`
- If `ENABLE_OPENAPI_DOCS=true` in `.env`, OpenAPI UI is at `/docs` or `/redoc`. Set `OPENAPI_DOCS_REQUIRE_AUTH=true` to restrict docs to authenticated users (JWT).

## Docker Compose (full stack)

Starts the API, **Celery worker**, **Celery beat**, **Redis**, **MinIO**, and **Mailpit** (captured email).

```bash
docker compose up --build -d
```

| Service   | URL |
|-----------|-----|
| API       | http://127.0.0.1:8000 |
| Mailpit   | http://127.0.0.1:8025 |
| MinIO UI  | http://127.0.0.1:9001 (credentials in `docker-compose.yml`) |

The API image installs from `requirements.txt` (pip). For day-to-day development, **Poetry** on the host is recommended.

## Environment variables

Copy [`.env.example`](.env.example) to `.env`. Highlights:

| Group | Purpose |
|-------|---------|
| `STRIPE_*` | Secret key, success/cancel URLs, currency, `STRIPE_WEBHOOK_SECRET` for `/webhooks/stripe` |
| `CELERY_*` / Redis | Broker and result backend for async tasks |
| `SMTP_*` | If `SMTP_HOST` is empty, outbound email is skipped (tasks log only) |
| `PUBLIC_BASE_URL` | Base URL used in emails (activation, password reset) |
| `ENABLE_OPENAPI_DOCS`, `OPENAPI_DOCS_REQUIRE_AUTH` | Swagger / ReDoc visibility |
| `ADMIN_BOOTSTRAP_*` | Optional first admin user when the database has no admins |

Optional variables (see `src/config/settings.py` for defaults) include `SECRET_KEY` / `SECRET_KEY_ACCESS`, `PATH_TO_DB`, `EXPOSE_DEV_AUTH_TOKENS`, and `ENVIRONMENT` (CI sets `testing`).

Do not commit secrets; keep `.env` out of version control.

## Optional data scripts

- `python -m src.database.populate` — inserts a small demo catalog (two movies and related rows).
- `python -m src.database.seed_payment_demo` — idempotent Stripe demo user + cart (see module docstring).

## Tests and quality gates

```bash
poetry run pytest src/tests/ -q
poetry run pytest src/tests/ --cov=src --cov-report=term-missing
poetry run black src
poetry run isort src
poetry run flake8 src
poetry run mypy src
```

CI (GitHub Actions) runs linters, **mypy**, and **pytest** with a coverage threshold.

## Repository layout

| Path | Description |
|------|-------------|
| `src/main.py` | FastAPI app factory and router includes |
| `src/auth/` | Registration, login, refresh, logout, passwords |
| `src/routes/` | HTTP routers (movies, cart, orders, payments, admin, …) |
| `src/database/` | SQLAlchemy models, session, DB initialization |
| `src/worker/` | Celery app, mail tasks, scheduled token purge |
| `src/tests/` | Pytest suite |
| `.github/workflows/` | CI/CD workflows |


