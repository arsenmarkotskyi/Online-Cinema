from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.auth.dependencies import get_current_user
from src.database.models import Movie, MovieComment, Notification, User
from src.database.session import get_db
from src.schemas.comments import CommentCreate, CommentRead

router = APIRouter(prefix="/comments", tags=["comments"])


@router.post("/", response_model=CommentRead, status_code=201)
async def create_comment(
    comment_in: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ensure the movie exists
    movie = await db.get(Movie, comment_in.movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    # If replying, validate parent comment belongs to the same movie
    if comment_in.parent_id:
        parent_comment = await db.get(MovieComment, comment_in.parent_id)
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Parent comment not found")

        if parent_comment.user_id != current_user.id:
            notification = Notification(
                user_id=parent_comment.user_id,
                message=(
                    f"{current_user.email} replied to your comment on "
                    f"'{movie.name}'"
                ),
            )
            db.add(notification)

    comment = MovieComment(
        user_id=current_user.id,
        movie_id=comment_in.movie_id,
        parent_id=comment_in.parent_id,
        text=comment_in.text,
    )
    db.add(comment)
    await db.commit()
    stmt = (
        select(MovieComment)
        .options(
            selectinload(MovieComment.replies),
            selectinload(MovieComment.user),
        )
        .where(MovieComment.id == comment.id)
    )
    result = await db.execute(stmt)
    fresh_comment = result.scalar_one()

    return fresh_comment
