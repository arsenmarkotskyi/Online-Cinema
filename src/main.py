from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.auth.routes import router as auth_router
from src.config.settings import get_settings
from src.database.session import close_db, init_db
from src.openapi_docs import register_openapi_documentation
from src.routes.admin import router as admin_router
from src.routes.cart import router as cart_router
from src.routes.certifications import router as certifications_router
from src.routes.comment_likes import router as comment_likes
from src.routes.comments import router as comments_router
from src.routes.directors import router as directors_router
from src.routes.favorites import router as favorites_router
from src.routes.genres import router as genres_router
from src.routes.movie_likes import router as likes_router
from src.routes.movies import router as movies_router
from src.routes.notifications import router as notifications_router
from src.routes.orders import router as orders_router
from src.routes.payments import router as payments_router
from src.routes.profile import router as profile_router
from src.routes.ratings import router as ratings_router
from src.routes.stars import router as stars_router
from src.routes.stripe_webhook import router as stripe_webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    """Build FastAPI app; calls ``get_settings()`` each time (tests, reloads)."""
    settings = get_settings()
    docs_enabled = settings.ENABLE_OPENAPI_DOCS

    openapi_tags = [
        {
            "name": "auth",
            "description": "Register, activate, JWT login, refresh, logout, passwords.",
        },
        {"name": "movies", "description": "Catalog: filters, search, sort, detail."},
        {"name": "likes", "description": "Movie likes and dislikes."},
        {"name": "comments", "description": "Movie comments and replies."},
        {"name": "comment-likes", "description": "Likes on comments."},
        {"name": "favorites", "description": "Favorites; search/sort like catalog."},
        {"name": "genres", "description": "Genres and movies by genre."},
        {"name": "certifications", "description": "Age ratings; moderator CRUD."},
        {"name": "directors", "description": "Directors; moderator CRUD."},
        {"name": "stars", "description": "Actors; moderator CRUD."},
        {"name": "ratings", "description": "User ratings (0–10)."},
        {"name": "cart", "description": "Shopping cart."},
        {"name": "orders", "description": "Orders, cancel pending, refunds when paid."},
        {"name": "payments", "description": "Stripe Checkout, history, session poll."},
        {"name": "webhooks", "description": "Stripe webhook for paid orders."},
        {"name": "profile", "description": "User profile."},
        {"name": "notifications", "description": "In-app notifications."},
        {"name": "admin", "description": "Moderator and admin tools."},
    ]

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        title="Online Cinema API",
        openapi_tags=openapi_tags,
    )

    app.include_router(movies_router)
    app.include_router(likes_router)
    app.include_router(auth_router)
    app.include_router(comments_router)
    app.include_router(favorites_router)
    app.include_router(genres_router)
    app.include_router(ratings_router)
    app.include_router(comment_likes)
    app.include_router(notifications_router)
    app.include_router(admin_router)
    app.include_router(cart_router)
    app.include_router(orders_router)
    app.include_router(directors_router)
    app.include_router(certifications_router)
    app.include_router(stars_router)
    app.include_router(profile_router)
    app.include_router(payments_router)
    app.include_router(stripe_webhook_router)

    if docs_enabled:
        register_openapi_documentation(
            app, require_auth=settings.OPENAPI_DOCS_REQUIRE_AUTH
        )

    return app


app = create_app()
