from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_moderator
from src.database.models import Star, User
from src.database.session import get_db
from src.schemas.stars import StarCreate, StarOut

router = APIRouter(prefix="/stars", tags=["stars"])


@router.get("/", response_model=list[StarOut])
async def list_stars(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Star).order_by(Star.name))
    return result.scalars().all()


@router.post("/", response_model=StarOut, status_code=status.HTTP_201_CREATED)
async def create_star(
    data: StarCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    existing = await db.execute(select(Star).where(Star.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Star already exists")
    star = Star(name=data.name)
    db.add(star)
    await db.commit()
    await db.refresh(star)
    return star


@router.put("/{star_id}", response_model=StarOut)
async def update_star(
    star_id: int,
    data: StarCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    star = await db.get(Star, star_id)
    if not star:
        raise HTTPException(status_code=404, detail="Star not found")
    star.name = data.name
    await db.commit()
    await db.refresh(star)
    return star


@router.delete("/{star_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_star(
    star_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    star = await db.get(Star, star_id)
    if not star:
        raise HTTPException(status_code=404, detail="Star not found")
    await db.delete(star)
    await db.commit()
