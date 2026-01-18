import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.serializers.fullentry import get_fullentry, async_get_fullentry
from api.serializers.slug_fullentry import slug_find_entry, query_find_entry
from api.types.fullentry import FullEntry
from api.auth import get_role_from_request_jwt, check_cookie_jwt

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/fullentries/{uid}")
def get(uid: str) -> FullEntry:
    return get_fullentry(uid)

@router.get("/slugfullentries/{type}/{commune}/{effector}")
async def get_slug_fullentries(req: Request, type: str, commune: str, effector: str, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry|None:
    role = await get_role_from_request_jwt(jwt)
    uid = await slug_find_entry(commune, effector, type)
    return await async_get_fullentry(uid, req, role, jwt)

@router.get("/queryfullentries/")
async def get_query_fullentries(req: Request, effector: str, facility: str, type: str, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry|None:
    role = await get_role_from_request_jwt(jwt)
    uid = await query_find_entry(effector, facility, type)
    return await async_get_fullentry(uid, req, role, jwt)

@router.get("/ftefullentries/{facility}/{type}/{effector}")
async def get_fte_fullentries(req: Request, effector: str, facility: str, type: str, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry|None:
    role = await get_role_from_request_jwt(jwt)
    uid = await query_find_entry(effector, facility, type)
    return await async_get_fullentry(uid, req, role, jwt)