from pydantic import BaseModel


class MovieLikeCreate(BaseModel):
    movie_id: int
    is_liked: bool
