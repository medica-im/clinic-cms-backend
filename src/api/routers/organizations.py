from fastapi import APIRouter, status
from api.serializers.organization import get_organizations, get_organization, create_organization
from api.types.organization import OrganizationPy

router = APIRouter()

@router.get("/organizations")
async def organizations() -> list[OrganizationPy]:
    return get_organizations()

@router.get("/organizations/{organization_uid}")
async def organization(organization_uid: str) -> OrganizationPy :
    return get_organization(uid=organization_uid)

@router.post("/organizations/", status_code=status.HTTP_201_CREATED)
async def post_organization(organization: OrganizationPy) -> OrganizationPy:
    return create_organization(organization.model_dump())