from pydantic import BaseModel


class MovieReactionBase(BaseModel):
    is_like: bool


class MovieReactionCreate(MovieReactionBase):
    pass


class MovieReactionRead(MovieReactionBase):
    id: int
    user_id: int
    movie_id: int

    class Config:
        from_attributes = True
