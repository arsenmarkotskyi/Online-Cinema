"""Seed data after schema creation: user groups and optional demo admin."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.security import hash_password
from src.config.settings import get_settings
from src.database.models import User, UserGroup, UserGroupEnum


async def seed_user_groups(session: AsyncSession) -> None:
    """Ensure ``USER``, ``MODERATOR``, and ``ADMIN`` rows exist in ``user_groups``."""
    for role in UserGroupEnum:
        result = await session.execute(select(UserGroup).where(UserGroup.name == role))
        if result.scalar_one_or_none() is None:
            session.add(UserGroup(name=role))
    await session.flush()


async def _any_admin_exists(session: AsyncSession) -> bool:
    result = await session.execute(
        select(User.id)
        .join(UserGroup, User.group_id == UserGroup.id)
        .where(UserGroup.name == UserGroupEnum.ADMIN)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def maybe_bootstrap_admin(session: AsyncSession) -> None:
    """
    If ``ADMIN_BOOTSTRAP_EMAIL`` and ``ADMIN_BOOTSTRAP_PASSWORD`` are set in settings
    and no admin user exists yet, create or promote that account to ``ADMIN``.

    Intended for local development and demos only.
    """
    settings = get_settings()
    email = settings.ADMIN_BOOTSTRAP_EMAIL
    password = settings.ADMIN_BOOTSTRAP_PASSWORD
    if not email or not password:
        return
    if await _any_admin_exists(session):
        return

    result = await session.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.ADMIN)
    )
    admin_group = result.scalar_one()

    result = await session.execute(select(User).where(User.email == email))
    user: User | None = cast(User | None, result.scalar_one_or_none())
    if user:
        user.group_id = admin_group.id
        user.is_active = True
        user.hashed_password = hash_password(password)
    else:
        session.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
                group_id=admin_group.id,
            )
        )
    await session.flush()
