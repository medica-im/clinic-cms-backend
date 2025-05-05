from fastapi import APIRouter
from directory.utils import get_organizations

router = APIRouter()

@router.get("/organizations")
async def organizations():
    return get_organizations()