from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.auth.dependencies import get_current_user
from src.database.models import MovieLike, User
from src.database.session import get_db
from src.schemas.movie_likes import MovieLikeCreate

router = APIRouter(prefix="/likes", tags=["likes"])


@router.post("/like")
async def like_movie(
    like_data: MovieLikeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(MovieLike).where(
        MovieLike.user_id == current_user.id,
        MovieLike.movie_id == like_data.movie_id,
    )
    existing = (await db.execute(stmt)).scalars().first()

    if existing:
        existing.is_liked = like_data.is_liked
    else:
        like = MovieLike(
            user_id=current_user.id,
            movie_id=like_data.movie_id,
            is_liked=like_data.is_liked,
        )
        db.add(like)

    try:
        await db.commit()
        return {"message": "Like status updated"}
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid like request")
