from fastapi import FastAPI
from api.routers import organizations

app = FastAPI()

app.include_router(organizations.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}