from fastapi import APIRouter
from pydantic import BaseModel
from directory.fastapi import get_organizations, create_organization

router = APIRouter()

class Organization(BaseModel):
    name_fr: str
    label_fr: str
    type: str
    organization: str | None = None
    commune: str
    website: str | None = None

@router.get("/organizations")
async def organizations():
    return get_organizations()

@router.get("/organizations/{organization_uid}")
async def organization(organization_uid: str):
    return get_organizations(uid=organization_uid)

@router.post("/organizations")
async def post_organization(organization: Organization):
    return create_organization(organization.model_dump())