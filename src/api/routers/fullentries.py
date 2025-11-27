import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.serializers.fullentry import get_fullentry, async_get_fullentry
from api.serializers.slug_fullentry import slug_find_entry, query_find_entry
from api.types.fullentry import FullEntry
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/fullentries/{uid}")
def get(uid: str) -> FullEntry:
    return get_fullentry(uid)

@router.get("/slugfullentries/{type}/{commune}/{effector}")
async def get_slug_fullentries(type: str, commune: str, effector: str) -> FullEntry|None:
    uid = await slug_find_entry(commune, effector, type)
    return await async_get_fullentry(uid)

@router.get("/queryfullentries/")
async def get_query_fullentries(effector: str, facility: str, type: str) -> FullEntry|None:
    uid = await query_find_entry(effector, facility, type)
    return await async_get_fullentry(uid)