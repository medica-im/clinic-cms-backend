import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.serializers.fullentry import get_fullentry, async_get_fullentry
from api.serializers.slug_fullentry import slug_find_entry, query_find_entry
from api.types.fullentry import FullEntry
from api.auth import get_role_from_jwt, check_cookie_jwt, JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/fullentries/{uid}")
async def get(uid: str, req: Request, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry:
    return await async_get_fullentry(uid, req, jwt)

@router.get("/slugfullentries/{type}/{commune}/{effector}")
async def get_slug_fullentries(req: Request, type: str, commune: str, effector: str, jwt: Annotated[dict, Depends(JWT)]) -> FullEntry|None:
    active=None
    uid = await slug_find_entry(commune, effector, type, active)
    return await async_get_fullentry(uid, req, jwt)

@router.get("/queryfullentries/")
async def get_query_fullentries(req: Request, effector: str, facility: str, type: str, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry|None:
    uid = await query_find_entry(effector, facility, type)
    return await async_get_fullentry(uid, req, jwt)

@router.get("/ftefullentries/{facility}/{type}/{effector}")
async def get_fte_fullentries(req: Request, effector: str, facility: str, type: str, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> FullEntry|None:
    uid = await query_find_entry(effector, facility, type)
    return await async_get_fullentry(uid, req, jwt)