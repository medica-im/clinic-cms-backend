from fastapi import APIRouter
from directory.fastapi import get_organizations

router = APIRouter()

@router.get("/organizations")
async def organizations():
    return get_organizations()

@router.get("/organizations/{organization_uid}")
async def organization(organization_uid: str):
    return get_organizations(uid=organization_uid)