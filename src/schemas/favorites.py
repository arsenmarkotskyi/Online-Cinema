from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    movie_id: int


class FavoriteRead(BaseModel):
    id: int
    movie_id: int
    user_id: int

    class Config:
        from_attributes = True
