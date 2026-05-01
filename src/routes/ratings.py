from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.database.models import Movie, Rating, User
from src.database.session import get_db
from src.schemas.ratings import RatingCreate, RatingOut

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.post("/", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
async def rate_movie(
    rating_in: RatingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    movie = await db.get(Movie, rating_in.movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    stmt = select(Rating).where(
        Rating.user_id == current_user.id, Rating.movie_id == rating_in.movie_id
    )
    result = await db.execute(stmt)
    existing_rating = result.scalar_one_or_none()

    if existing_rating:
        existing_rating.score = rating_in.score
    else:
        rating = Rating(
            user_id=current_user.id, movie_id=rating_in.movie_id, score=rating_in.score
        )
        db.add(rating)

    await db.commit()

    return rating_in
