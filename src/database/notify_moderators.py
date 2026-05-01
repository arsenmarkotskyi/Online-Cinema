"""Send in-app notifications to all MODERATOR and ADMIN users."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Notification, User, UserGroup, UserGroupEnum


async def notify_moderators(db: AsyncSession, message: str) -> None:
    """Append the same message as a Notification row for each moderator and admin."""
    stmt = (
        select(User.id)
        .join(UserGroup, User.group_id == UserGroup.id)
        .where(UserGroup.name.in_((UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN)))
    )
    rows = (await db.execute(stmt)).scalars().all()
    for uid in rows:
        db.add(Notification(user_id=uid, message=message))
