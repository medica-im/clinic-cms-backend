from fastapi import APIRouter
from pydantic import BaseModel
from directory.fastapi import get_organization_types

router = APIRouter()

class OrganizationType(BaseModel):
    name_fr: str
    label_fr: str
    synonyms_fr: str
    organization_type: str | None

@router.get("/organization-types")
async def organization_types():
    return get_organization_types()

@router.get("/organization-types/{organization_type_uid}")
async def organization_type(organization_type_uid: str):
    return get_organization_types(uid=organization_type_uid)