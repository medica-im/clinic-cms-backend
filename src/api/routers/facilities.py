from fastapi import APIRouter, status
from api.serializers.facility import get_facilities, get_facility
from api.types.facility import Facility

router = APIRouter()

@router.get("/facilities")
async def facilities() -> list[Facility]:
    return get_facilities()

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return get_facility(uid=uid)
"""
@router.post("/organizations/", status_code=status.HTTP_201_CREATED)
async def post_organization(organization: OrganizationPy) -> OrganizationPy:
    return create_organization(organization.model_dump())
"""