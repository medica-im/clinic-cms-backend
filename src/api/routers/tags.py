import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from django.db.utils import DatabaseError, IntegrityError
from addressbook.models import PhoneNumber, Contact
from access.models import Role
from api.types.tag import Tag, TagCategory, TagEntry
from api.auth import JWT
from api.auth import authorize_api
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
    await authorize_api("entry_tag_v2", request, jwt)
    return await update_tags(item)

