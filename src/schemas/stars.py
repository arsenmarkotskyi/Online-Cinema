from pydantic import BaseModel


class StarCreate(BaseModel):
    name: str


class StarOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
