from fastapi import FastAPI
from directory.utils import get_organizations

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/organizations")
async def organizations():
    return get_organizations()