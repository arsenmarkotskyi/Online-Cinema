from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_moderator
from src.database.models import Director, User
from src.database.session import get_db
from src.schemas.directors import DirectorCreate, DirectorOut

router = APIRouter(prefix="/directors", tags=["directors"])


@router.get("/", response_model=list[DirectorOut])
async def list_directors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Director).order_by(Director.name))
    return result.scalars().all()


@router.post("/", response_model=DirectorOut, status_code=status.HTTP_201_CREATED)
async def create_director(
    data: DirectorCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    existing = await db.execute(select(Director).where(Director.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Director already exists")
    director = Director(name=data.name)
    db.add(director)
    await db.commit()
    await db.refresh(director)
    return director


@router.put("/{director_id}", response_model=DirectorOut)
async def update_director(
    director_id: int,
    data: DirectorCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    director = await db.get(Director, director_id)
    if not director:
        raise HTTPException(status_code=404, detail="Director not found")
    director.name = data.name
    await db.commit()
    await db.refresh(director)
    return director


@router.delete("/{director_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_director(
    director_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    director = await db.get(Director, director_id)
    if not director:
        raise HTTPException(status_code=404, detail="Director not found")
    await db.delete(director)
    await db.commit()
