import logging
from fastapi import APIRouter, status
from api.serializers.facility import get_facilities, get_facility, create_facility, delete_facility
from api.types.facility import Facility, FacilityPost
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/facilities")
async def facilities() -> list[Facility]:
    return get_facilities()

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return get_facility(uid=uid)

@router.post("/facilities/", status_code=status.HTTP_201_CREATED)
async def post_facility(facility: FacilityPost) -> Facility:
    return create_facility(facility.model_dump())

@router.delete("/facilities/{uid}", status_code=status.HTTP_200_OK)
async def delete(uid: str):
    return delete_facility(uid)