import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from django.db.utils import DatabaseError, IntegrityError
from addressbook.models import PhoneNumber, Contact
from access.models import Role
from api.types.tag import Tag, TagCategory
from api.auth import JWT
from api.auth import authorize_api
from api.serializers.tags import tag_categories, tag_category, tags

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/tag_categories", response_model=list[TagCategory])
async def get_tag_categories():
    return await tag_categories()

@router.get("/tag_categories/{uid}")
async def get_tag_category(uid: str) -> TagCategory:
    return await tag_category(uid)

@router.get("/tags", response_model=list[Tag])
async def get_tags(category: str|None):
    return await tags(category)
