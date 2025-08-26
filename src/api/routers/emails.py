import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import Email as DjangoEmail, Contact
from django.db.utils import DatabaseError
from access.models import Role
from api.types.email import Email, EmailPost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/emails/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("emails_v2", request, jwt)
    try:
        await DjangoEmail.objects.filter(id=item_id).adelete()
    except DjangoEmail.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Email not found")

@router.put("/emails/{item_id}", response_model=Email)
async def update_item(item_id: str, item: Email, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("emails_v2", request, jwt)
    logger.debug(item)
    i = jsonable_encoder(item)
    logger.debug(i)
    try:
        email = await DjangoEmail.objects.select_related('contact').aget(id=item_id)
    except DjangoEmail.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Email not found")
    logger.debug(i)
    email.email=i['email']
    await email.asave()
    await set_roles(email,i['roles'] )
    logger.debug(email)
    return i

@router.get("/emails/{item_id}", response_model=Email)
async def get_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("emails_v2", request, jwt)
    try:
        email = await DjangoEmail.objects.aget(id=item_id)
    except DjangoEmail.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Email not found")
    return email

@router.post("/emails/", response_model=Email)
async def create_item(item: EmailPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("emails_v2", request, jwt)
    i = item.model_dump()
    try:
        contact = await Contact.objects.aget(neomodel_uid=i['entry'])
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {i['entry']} not found")
    roles_qs=Role.objects.filter(name__in=i['roles'])
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    try:
        email = await DjangoEmail.objects.acreate(
            contact = contact,
            email = i['email'],
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
    await email.asave()
    if roles:
        await email.roles.aset(roles)
    i['id']=email.pk
    return i
