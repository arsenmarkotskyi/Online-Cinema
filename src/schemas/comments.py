from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CommentBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class CommentCreate(CommentBase):
    movie_id: int
    parent_id: Optional[int] = None


class CommentRead(CommentBase):
    id: int
    user_id: int
    movie_id: int
    parent_id: Optional[int]
    created_at: datetime
    replies: List["CommentRead"] = []

    class Config:
        from_attributes = True


CommentRead.model_rebuild()
