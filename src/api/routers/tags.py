import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from api.types.tag import Tag, TagCategory, TagEntry
from api.auth import JWT, authorize_api
from api.utils import get_entry, get_entry_users
from api.serializers.tags import tag_categories, tag_category, tags, update_tags

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/tag_categories", response_model=list[TagCategory])
async def get_tag_categories():
    return await tag_categories()

@router.get("/tag_categories/{uid}")
async def get_tag_category(uid: str) -> TagCategory:
    return await tag_category(uid)

@router.get("/tags", response_model=list[Tag])
async def get_tags(category: str|None=None):
    return await tags(category)

@router.post("/entry/tag")
async def post_entry_tags(item: TagEntry, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    entry = await get_entry(item.entry)
    users = await get_entry_users(entry)
    await authorize_api("entry_tag_v2", request, jwt, users=users)
    return await update_tags(item)

