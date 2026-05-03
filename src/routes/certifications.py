from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_moderator
from src.database.models import Certification, Movie, User
from src.database.session import get_db
from src.schemas.certifications import CertificationCreate, CertificationOut

router = APIRouter(prefix="/certifications", tags=["certifications"])


@router.get("/", response_model=list[CertificationOut])
async def list_certifications(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Certification).order_by(Certification.name))
    return result.scalars().all()


@router.post("/", response_model=CertificationOut, status_code=status.HTTP_201_CREATED)
async def create_certification(
    data: CertificationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    existing = await db.execute(
        select(Certification).where(Certification.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Certification already exists")
    row = Certification(name=data.name)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{certification_id}", response_model=CertificationOut)
async def update_certification(
    certification_id: int,
    data: CertificationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    row = await db.get(Certification, certification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")
    dup = await db.execute(
        select(Certification).where(
            and_(Certification.name == data.name, Certification.id != certification_id)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Certification name already exists")
    row.name = data.name
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{certification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    certification_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_moderator),
):
    row = await db.get(Certification, certification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")
    in_use = await db.execute(
        select(func.count())
        .select_from(Movie)
        .where(Movie.certification_id == certification_id)
    )
    if (in_use.scalar_one() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete certification: one or more movies still reference it."
            ),
        )
    await db.delete(row)
    await db.commit()
