from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class CartItemOut(BaseModel):
    movie_id: int
    name: str
    year: int
    price: float
    genres: List[str] = Field(default_factory=list)
    added_at: datetime | None = None


class CartOut(BaseModel):
    items: List[CartItemOut]
    subtotal: float
