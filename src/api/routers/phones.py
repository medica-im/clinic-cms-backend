import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import PhoneNumber, Contact
from access.models import Role
from api.types.phones import Phone, PhonePost
from api.auth import JWT
from api.auth import authorize_api

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/phones/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    try:
        await PhoneNumber.objects.filter(id=item_id).adelete()
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")

@router.put("/phones/{item_id}", response_model=Phone)
async def update_item(item_id: str, item: Phone, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    logger.debug(item)
    i = jsonable_encoder(item)
    try:
        phone_number = await PhoneNumber.objects.select_related('contact').aget(id=item_id)
        logger.debug(phone_number)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")
    phone_number.type=i['type']
    phone_number.phone=i['phone']
    await phone_number.asave()
    roles_qs=Role.objects.filter(name__in=i['roles'])
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    if roles:
        await phone_number.roles.aset(roles)
    logger.debug(f'after aset: {phone_number.roles.all()}')
    return i

@router.get("/phones/{item_id}", response_model=Phone)
async def get_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    try:
        phone_number = await PhoneNumber.objects.aget(id=item_id)
        logger.debug(phone_number)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")
    return phone_number

@router.post("/phones/", response_model=Phone)
async def create_item(item: PhonePost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    logger.debug(item)
    i = item.model_dump()
    logger.debug(i)
    try:
        contact = await Contact.objects.aget(neomodel_uid=i['entry'])
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {i['entry']} not found")
    roles_qs=Role.objects.filter(name__in=i['roles'])
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    logger.debug(f'{roles=}')
    try:
        phone_number = await PhoneNumber.objects.acreate(
            contact = contact,
            phone = i['phone'],
            type = i['type']
        )
        logger.debug(phone_number)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")
    await phone_number.asave()
    if roles:
        await phone_number.roles.aset(roles)
    i['id']=phone_number.pk
    return i
