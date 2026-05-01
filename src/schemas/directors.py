from pydantic import BaseModel


class DirectorCreate(BaseModel):
    name: str


class DirectorOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
