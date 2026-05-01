from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.auth.dependencies import get_current_user
from src.database.models import CommentLike, MovieComment, Notification, User
from src.database.session import get_db

router = APIRouter(prefix="/comment-likes", tags=["comment-likes"])


@router.post("/{comment_id}")
async def like_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = await db.get(MovieComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    stmt = select(CommentLike).where(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    existing_like = result.scalar_one_or_none()

    if existing_like:
        raise HTTPException(status_code=400, detail="You already liked this comment")

    like = CommentLike(user_id=current_user.id, comment_id=comment_id)
    db.add(like)

    await db.refresh(comment, ["movie"])

    if comment.user_id != current_user.id:
        notification = Notification(
            user_id=comment.user_id,
            message=(
                f"{current_user.email} liked your comment on " f"'{comment.movie.name}'"
            ),
        )
        db.add(notification)

    await db.commit()
    return {"message": "Comment liked successfully"}
