from typing import Annotated

from pydantic import BaseModel, Field


class RatingCreate(BaseModel):
    movie_id: int
    score: Annotated[int, Field(ge=1, le=10)]


class RatingOut(BaseModel):
    movie_id: int
    score: int

    class Config:
        from_attributes = True
