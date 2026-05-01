from pydantic import BaseModel


class GenreWithCountOut(BaseModel):
    id: int
    name: str
    movie_count: int


class GenreCreate(BaseModel):
    name: str


class GenreOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
