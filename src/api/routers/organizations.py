from fastapi import APIRouter, status
from pydantic import BaseModel
from directory.fastapi import get_organizations, get_organization, create_organization
from api.types.organization import OrganizationPy

router = APIRouter()

class Organization(BaseModel):
    name_fr: str
    label_fr: str
    type: str
    organization: str | None = None
    commune: str
    website: str | None = None

exclude_keys = {
    'element_id_property': True,
    'name_en': True,
    'label_en': True
}

@router.get("/organizations")
async def organizations() -> list[OrganizationPy]:
    return get_organizations()

@router.get("/organizations/{organization_uid}")
async def organization(organization_uid: str) -> OrganizationPy :
    return get_organization(uid=organization_uid)

@router.post("/organizations/", status_code=status.HTTP_201_CREATED)
async def post_organization(organization: Organization):
    return create_organization(organization.model_dump())