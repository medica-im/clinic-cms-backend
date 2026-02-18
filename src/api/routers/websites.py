import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import Website as DjangoWebsite, Contact
from django.db.utils import DatabaseError, IntegrityError
from access.models import Role
from api.types.website import Website, WebsitePost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles, get_entry, get_entry_users

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/websites/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        obj = await DjangoWebsite.objects.select_related('contact').aget(id=item_id)
    except DjangoWebsite.DoesNotExist:
        raise HTTPException(status_code=404, detail="Website not found")
    if not obj.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(obj.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("websites_v2", request, jwt, users=users)
    await DjangoWebsite.objects.filter(id=item_id).adelete()

@router.put("/websites/{item_id}", response_model=Website)
async def update_item(item_id: str, item: Website, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    i = jsonable_encoder(item)
    try:
        obj = await DjangoWebsite.objects.select_related('contact').aget(id=item_id)
    except DjangoWebsite.DoesNotExist:
        raise HTTPException(status_code=404, detail="Website not found")
    if not obj.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(obj.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("websites_v2", request, jwt, users=users)
    obj.url=i['url']
    await obj.asave()
    await set_roles(obj, i['roles'])
    return i

@router.get("/websites/{item_id}", response_model=Website)
async def get_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("websites_v2", request, jwt)
    try:
        obj = await DjangoWebsite.objects.aget(id=item_id)
    except DjangoWebsite.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Object not found")
    return obj

@router.post("/websites/", response_model=Website)
async def create_item(item: WebsitePost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    entry = await get_entry(item.entry)
    users = await get_entry_users(entry)
    await authorize_api("websites_v2", request, jwt, users=users)
    i = item.model_dump()
    try:
        contact = await Contact.objects.aget(neomodel_uid=item.entry)
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {item.entry} not found")
    try:
        obj = await DjangoWebsite.objects.acreate(
            contact = contact,
            url = i['url'],
        )
    except IntegrityError as e:
        logger.debug(f"{e}")
        raise HTTPException(status_code=409, detail=f"Le site {i['url']} existe déjà pour cette entrée.")
    await obj.asave()
    await set_roles(obj, i['roles'])
    i['id']=obj.pk
    return i
