import os
import logging
from typing import Annotated, Union
from fastapi import APIRouter, status, Depends, Request, HTTPException
from api.serializers.facility import get_facilities, get_facility, create_facility, update_facility, delete_facility
from api.types.facility import Facility, FacilityPost, FacilityPut
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/facilities")
async def facilities() -> list[Facility]:
    return get_facilities()

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return get_facility(uid=uid)

@router.post("/facilities/", status_code=status.HTTP_201_CREATED)
async def post_facility(facility: FacilityPost, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    logger.debug(f'${facility=}')
    await authorize_api("facilities_v2", request, jwt)
    return create_facility(facility)

@router.put("/facilities/{uid}", status_code=status.HTTP_201_CREATED)
async def put_facility(uid: str, facility: FacilityPut, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    await authorize_api("facilities_v2", request, jwt)
    return update_facility(uid, facility)

@router.delete("/facilities/{uid}")
async def delete(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("facilities_v2", request, jwt)
    return await delete_facility(uid)