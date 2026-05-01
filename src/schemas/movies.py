from typing import List, Optional

from pydantic import BaseModel


class MovieBase(BaseModel):
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: str
    price: Optional[float] = None
    certification_id: int


class MovieCreate(MovieBase):
    genre_ids: List[int] = []
    director_ids: List[int] = []
    star_ids: List[int] = []


class MovieRead(MovieBase):
    id: int
    uuid: str

    class Config:
        from_attributes = True


class GenreOut(BaseModel):
    name: str

    class Config:
        from_attributes = True


class StarOut(BaseModel):
    name: str

    class Config:
        from_attributes = True


class DirectorOut(BaseModel):
    name: str

    class Config:
        from_attributes = True


class MovieShortOut(BaseModel):
    id: int
    name: str
    year: Optional[int] = None

    class Config:
        from_attributes = True


class MovieDetailOut(MovieBase):
    id: int
    uuid: str  # Якщо потрібно
    genres: List[GenreOut] = []
    directors: List[DirectorOut] = []
    stars: List[StarOut] = []

    class Config:
        from_attributes = True
