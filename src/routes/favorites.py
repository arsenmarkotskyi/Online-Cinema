from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased

from src.auth.dependencies import get_current_user
from src.database.models import Favorite, Movie, User
from src.database.session import get_db
from src.schemas.movies import MovieShortOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.post("/{movie_id}", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    movie = await db.get(Movie, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    # Перевірити чи вже є у фаворитах
    stmt = select(Favorite).where(
        Favorite.user_id == current_user.id, Favorite.movie_id == movie_id
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Movie already in favorites")

    favorite = Favorite(user_id=current_user.id, movie_id=movie_id)
    db.add(favorite)
    await db.commit()
    return {"detail": "Movie added to favorites"}


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Favorite).where(
        Favorite.user_id == current_user.id, Favorite.movie_id == movie_id
    )
    result = await db.execute(stmt)
    favorite = result.scalars().first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Movie not in favorites")

    await db.delete(favorite)
    await db.commit()
    return


@router.get("/", response_model=List[MovieShortOut])
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    year: Optional[int] = Query(None),
    min_imdb: Optional[float] = Query(None),
    max_imdb: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
):
    offset = (page - 1) * per_page

    favorite_alias = aliased(Favorite)

    query = (
        select(Movie)
        .join(favorite_alias, Movie.id == favorite_alias.movie_id)
        .where(favorite_alias.user_id == current_user.id)
    )

    if year:
        query = query.where(Movie.year == year)
    if min_imdb:
        query = query.where(Movie.imdb >= min_imdb)
    if max_imdb:
        query = query.where(Movie.imdb <= max_imdb)
    if search:
        ilike = f"%{search.lower()}%"
        query = query.where(
            or_(Movie.name.ilike(ilike), Movie.description.ilike(ilike))
        )

    if sort_by:
        is_desc = sort_by.startswith("-")
        field = sort_by.lstrip("-")
        if hasattr(Movie, field):
            sort_field = getattr(Movie, field)
            query = query.order_by(desc(sort_field) if is_desc else asc(sort_field))

    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    movies = result.scalars().all()
    return movies
