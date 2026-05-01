from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_moderator
from src.database.models import Genre, User, movie_genres
from src.database.session import get_db
from src.schemas.genres import GenreCreate, GenreOut, GenreWithCountOut
from src.schemas.movies import MovieShortOut

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get("/", response_model=list[GenreWithCountOut])
async def list_genres_with_counts(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(
            Genre.id,
            Genre.name,
            func.count(movie_genres.c.movie_id).label("movie_count"),
        )
        .join(movie_genres, Genre.id == movie_genres.c.genre_id, isouter=True)
        .group_by(Genre.id)
        .order_by(Genre.name)
    )
    result = await db.execute(stmt)
    genres = result.all()
    return [
        GenreWithCountOut(id=g.id, name=g.name, movie_count=g.movie_count or 0)
        for g in genres
    ]


@router.get("/{genre_id}/movies", response_model=list[MovieShortOut])
async def list_movies_by_genre(genre_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Genre).options(selectinload(Genre.movies)).where(Genre.id == genre_id)
    result = await db.execute(stmt)
    genre = result.scalar_one_or_none()
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    return genre.movies


@router.post("/", response_model=GenreOut, status_code=status.HTTP_201_CREATED)
async def create_genre(
    data: GenreCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    existing = await db.execute(select(Genre).where(Genre.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Genre already exists")
    genre = Genre(name=data.name)
    db.add(genre)
    await db.commit()
    await db.refresh(genre)
    return genre


@router.put("/{genre_id}", response_model=GenreOut)
async def update_genre(
    genre_id: int,
    data: GenreCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    genre = await db.get(Genre, genre_id)
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    dup = await db.execute(
        select(Genre).where(and_(Genre.name == data.name, Genre.id != genre_id))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Genre name already exists")
    genre.name = data.name
    await db.commit()
    await db.refresh(genre)
    return genre


@router.delete("/{genre_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_genre(
    genre_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    genre = await db.get(Genre, genre_id)
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    in_use = await db.execute(
        select(func.count())
        .select_from(movie_genres)
        .where(movie_genres.c.genre_id == genre_id)
    )
    if (in_use.scalar_one() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete genre: one or more movies are still linked to it.",
        )
    await db.delete(genre)
    await db.commit()
