import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import SocialNetwork, Contact
from django.db.utils import DatabaseError, IntegrityError
from access.models import Role
from api.types.socialmedia import SocialMedia, SocialMediaPut, SocialMediaPost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles
from addressbook.api.serializers import AsyncSocialNetworkSerializer

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/socialmediatypes")
async def get_types():
    return SocialNetwork.SocialNetworkType.choices

@router.delete("/socialmedia/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("socialmedia_v2", request, jwt)
    try:
        await SocialNetwork.objects.filter(id=item_id).adelete()
    except SocialNetwork.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"SocialNetwork not found")

@router.put("/socialmedia/{item_id}", response_model=SocialMedia)
async def update_item(item_id: str, item: SocialMediaPut, request: Request, jwt: Annotated[dict, Depends(JWT)])->SocialMedia:
    await authorize_api("socialmedia_v2", request, jwt)
    try:
        obj = await SocialNetwork.objects.aget(id=item_id)
    except SocialNetwork.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"SocialNetwork not found")
    obj.url=item.url
    obj.type=item.type
    await obj.asave()
    await set_roles(obj, item.roles )
    serializer = AsyncSocialNetworkSerializer(obj)
    return SocialMedia.model_validate(serializer.data)

@router.get("/socialmedia/{item_id}", response_model=SocialMedia)
async def get_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)])->SocialMedia:
    await authorize_api("socialmedia_v2", request, jwt)
    try:
        obj = await SocialNetwork.objects.aget(id=item_id)
    except SocialNetwork.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Object not found")
    serializer = AsyncSocialNetworkSerializer(obj)
    data = await serializer.adata
    return SocialMedia.model_validate(data)

@router.post("/socialmedia/", response_model=SocialMedia)
async def create_item(item: SocialMediaPost, request: Request, jwt: Annotated[dict, Depends(JWT)])->SocialMedia:
    logger.debug(f"{item=}")
    await authorize_api("socialmedia_v2", request, jwt)
    try:
        contact = await Contact.objects.aget(neomodel_uid=item.entry)
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {item.entry} not found")
    try:
        obj = await SocialNetwork.objects.acreate(
            contact = contact,
            url = item.url,
            type = item.type,
        )
    except IntegrityError as e:
        logger.debug(f"{e}")
        raise HTTPException(status_code=409, detail=f"Le site {item.url} existe déjà pour cette entrée.")
    await obj.asave()
    await set_roles(obj, item.roles)
    serializer = AsyncSocialNetworkSerializer(obj)
    return SocialMedia.model_validate(await serializer.adata)
