from fastapi import APIRouter
from directory.fastapi import get_organizations

router = APIRouter()

@router.get("/organizations")
async def organizations():
    return get_organizations()