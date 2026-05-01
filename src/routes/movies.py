from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_moderator
from src.database.models import (
    CartItem,
    Director,
    Genre,
    Movie,
    MovieLike,
    OrderItem,
    Star,
    User,
)
from src.database.notify_moderators import notify_moderators
from src.database.session import get_db
from src.schemas.movies import MovieCreate, MovieDetailOut, MovieRead, MovieShortOut

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("/", response_model=List[MovieShortOut])
async def list_movies(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    year: int = Query(None, description="Filter by release year"),
    min_imdb: float = Query(None, description="Minimum IMDb rating"),
    max_imdb: float = Query(None, description="Maximum IMDb rating"),
    search: str = Query(None, description="Search by name or description"),
    sort_by: str = Query(None, description="Sort field, use '-' prefix for descending"),
):
    offset = (page - 1) * per_page
    query = select(Movie).options(
        selectinload(Movie.genres),
        selectinload(Movie.stars),
        selectinload(Movie.directors),
    )

    if year:
        query = query.where(Movie.year == year)
    if min_imdb:
        query = query.where(Movie.imdb >= min_imdb)
    if max_imdb:
        query = query.where(Movie.imdb <= max_imdb)
    if search:
        ilike_pattern = f"%{search.lower()}%"
        query = query.join(Movie.stars, isouter=True).join(
            Movie.directors, isouter=True
        )
        query = query.where(
            or_(
                Movie.name.ilike(ilike_pattern),
                Movie.description.ilike(ilike_pattern),
                Star.name.ilike(ilike_pattern),
                Director.name.ilike(ilike_pattern),
            )
        )

    if sort_by:
        is_desc = sort_by.startswith("-")
        field = sort_by.lstrip("-")
        if field == "popularity":
            like_count_sq = (
                select(func.count(MovieLike.id))
                .where(
                    MovieLike.movie_id == Movie.id,
                    MovieLike.is_liked.is_(True),
                )
                .scalar_subquery()
            )
            query = query.order_by(
                desc(like_count_sq) if is_desc else asc(like_count_sq)
            )
        elif hasattr(Movie, field):
            sort_field = getattr(Movie, field)
            query = query.order_by(desc(sort_field) if is_desc else asc(sort_field))
    else:
        query = query.order_by(Movie.id.asc())
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    movies = result.scalars().all()
    return movies


@router.get("/{movie_id}", response_model=MovieDetailOut)
async def get_movie(
    movie_id: int = Path(..., description="ID of the movie to retrieve"),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.directors),
            selectinload(Movie.stars),
            selectinload(Movie.certification),
        )
        .where(Movie.id == movie_id)
    )

    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    return MovieDetailOut.model_validate(movie)


async def build_movie(movie_data: MovieCreate, db: AsyncSession) -> dict:
    genres: list[Genre] = []
    directors: list[Director] = []
    stars: list[Star] = []

    if movie_data.genre_ids:
        genres = list(
            (await db.execute(select(Genre).where(Genre.id.in_(movie_data.genre_ids))))
            .scalars()
            .all()
        )

    if movie_data.director_ids:
        directors = list(
            (
                await db.execute(
                    select(Director).where(Director.id.in_(movie_data.director_ids))
                )
            )
            .scalars()
            .all()
        )

    if movie_data.star_ids:
        stars = list(
            (await db.execute(select(Star).where(Star.id.in_(movie_data.star_ids))))
            .scalars()
            .all()
        )

    return {
        "name": movie_data.name,
        "year": movie_data.year,
        "time": movie_data.time,
        "imdb": movie_data.imdb,
        "votes": movie_data.votes,
        "meta_score": movie_data.meta_score,
        "gross": movie_data.gross,
        "description": movie_data.description,
        "price": movie_data.price,
        "certification_id": movie_data.certification_id,
        "available_for_purchase": movie_data.available_for_purchase,
        "genres": genres,
        "directors": directors,
        "stars": stars,
    }


@router.post("/", response_model=MovieRead, status_code=201)
async def create_movie(
    movie_data: MovieCreate,
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
) -> MovieRead:
    exists_stmt = select(Movie).where(
        Movie.name == movie_data.name,
        Movie.year == movie_data.year,
        Movie.time == movie_data.time,
    )
    if (await db.execute(exists_stmt)).scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Movie with the same name, year and time already exists.",
        )

    movie_fields = await build_movie(movie_data, db)
    movie = Movie(**movie_fields)
    db.add(movie)
    await db.flush()

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Failed to create movie.")

    result = await db.execute(
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.directors),
            selectinload(Movie.stars),
        )
        .where(Movie.id == movie.id)
    )
    return MovieRead.model_validate(result.scalar_one())


@router.put("/{movie_id}", response_model=MovieRead)
async def update_movie(
    movie_id: int,
    movie_data: MovieCreate,
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
) -> MovieRead:
    stmt = (
        select(Movie)
        .where(Movie.id == movie_id)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.directors),
            selectinload(Movie.stars),
        )
    )
    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    # Enforce unique (name, year, time) vs other rows
    conflict_stmt = select(Movie).where(
        Movie.name == movie_data.name,
        Movie.year == movie_data.year,
        Movie.time == movie_data.time,
        Movie.id != movie_id,
    )
    if (await db.execute(conflict_stmt)).scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Another movie with the same name, year, and time already exists.",
        )

    # Apply scalar field updates
    movie_fields = await build_movie(movie_data, db)
    for key, value in movie_fields.items():
        setattr(movie, key, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Failed to update movie.")

    return MovieRead.model_validate(movie)


@router.delete("/{movie_id}", status_code=204)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    _moderator: User = Depends(require_moderator),
) -> None:
    """
    Delete a movie. Forbidden if the title appears in any order line
    (purchases or pending), or in any user cart; moderators are notified on
    cart conflict.
    """
    stmt = select(Movie).where(Movie.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    blocked = await db.execute(
        select(OrderItem.id).where(OrderItem.movie_id == movie_id).limit(1)
    )
    if blocked.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete movie: it is referenced by one or more orders "
                "(including purchases)."
            ),
        )

    cart_count = await db.execute(
        select(func.count(CartItem.id)).where(CartItem.movie_id == movie_id)
    )
    n_in_carts = int(cart_count.scalar_one() or 0)
    if n_in_carts > 0:
        await notify_moderators(
            db,
            (
                f"Delete attempt blocked: movie id={movie_id} «{movie.name}» "
                f"is in {n_in_carts} cart line(s). "
                "Ask users to remove it or clear those carts before deletion."
            ),
        )
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete movie: it is still in one or more user carts. "
                "Moderators have been notified."
            ),
        )

    await db.delete(movie)
    await db.commit()
