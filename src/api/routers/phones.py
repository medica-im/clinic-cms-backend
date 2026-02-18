import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from django.db.utils import DatabaseError, IntegrityError
from addressbook.models import PhoneNumber, Contact
from access.models import Role
from api.types.phones import Phone, PhonePost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import clear_cache, set_roles, get_entry, get_entry_users

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/phones/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        phone = await PhoneNumber.objects.select_related('contact').aget(id=item_id)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail="PhoneNumber not found")
    if not phone.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(phone.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("phones_v2", request, jwt, users=users)
    await PhoneNumber.objects.filter(id=item_id).adelete()

@router.put("/phones/{item_id}", response_model=Phone)
async def update_item(item_id: str, item: Phone, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    i = jsonable_encoder(item)
    try:
        phone = await PhoneNumber.objects.select_related('contact').aget(id=item_id)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail="PhoneNumber not found")
    if not phone.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(phone.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("phones_v2", request, jwt, users=users)
    phone.type=i['type']
    phone.phone=i['phone']
    try:
        await phone.asave()
    except IntegrityError as e:
        logger.debug(f"{e}")
        raise HTTPException(status_code=409, detail=f"Le numéro de téléphone {i['phone']} associé au type {i['type']} existe déjà pour cette entrée.")
    await set_roles(phone, i['roles'])
    await clear_cache('v2:entries', request)
    return i

@router.get("/phones/{item_id}", response_model=Phone)
async def get_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    try:
        phone_number = await PhoneNumber.objects.aget(id=item_id)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail="PhoneNumber not found")
    return phone_number

@router.post("/phones/", response_model=Phone)
async def create_item(item: PhonePost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    entry = await get_entry(item.entry)
    users = await get_entry_users(entry)
    await authorize_api("phones_v2", request, jwt, users=users)
    i = item.model_dump()
    try:
        contact = await Contact.objects.aget(neomodel_uid=item.entry)
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {item.entry} not found")
    try:
        phone_number = await PhoneNumber.objects.acreate(
            contact = contact,
            phone = i['phone'],
            type = i['type']
        )
    except IntegrityError as e:
        logger.debug(f"{e}")
        raise HTTPException(status_code=409, detail=f"Le numéro de téléphone {i['phone']} associé au type {i['type']} existe déjà pour cette entrée.")
    await phone_number.asave()
    await set_roles(phone_number, item.roles)
    i['id']=phone_number.pk
    await clear_cache('v2:entries', request)
    return i
