from fastapi import FastAPI

cinema = FastAPI()

@cinema.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}
