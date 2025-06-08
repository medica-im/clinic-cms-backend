from fastapi import APIRouter
from api.serializers.organization import get_organization_types, get_organization_type
from api.types.organization_types import OrganizationTypePy
from pydantic import ValidationError

router = APIRouter()

@router.get("/organization-types")
async def organization_types() -> list[OrganizationTypePy]:
    return get_organization_types()

@router.get("/organization-types/{uid}")
async def organization_type(uid: str)->OrganizationTypePy:
    return get_organization_type(uid=uid)