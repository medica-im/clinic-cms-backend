import os
import logging
from typing import Annotated
from fastapi import APIRouter, status, Depends, Request
from api.serializers.facility import get_facilities, get_facility, create_facility, delete_facility
from api.types.facility import Facility, FacilityPost
from api.auth import authorize_api
from fastapi_nextauth_jwt import NextAuthJWT

logger = logging.getLogger(__name__)

router = APIRouter()

auth_secret=os.getenv("AUTH_SECRET")
if auth_secret:
    JWT = NextAuthJWT(secret=auth_secret)

@router.get("/facilities")
async def facilities() -> list[Facility]:
    return get_facilities()

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return get_facility(uid=uid)

@router.post("/facilities/", status_code=status.HTTP_201_CREATED)
async def post_facility(facility: FacilityPost) -> Facility:
    logger.debug(facility.model_dump())
    return create_facility(facility.model_dump())

@router.delete("/facilities/{uid}")
async def delete(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("facilities_v2", request, jwt)
    return delete_facility(uid)