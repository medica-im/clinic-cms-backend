import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from addressbook.models import Email as DjangoEmail, Contact
from django.db.utils import DatabaseError, IntegrityError
from access.models import Role
from api.types.email import Email, EmailPost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles, get_entry, get_entry_users

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/emails/{item_id}")
async def delete_item(item_id: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        email = await DjangoEmail.objects.select_related('contact').aget(id=item_id)
    except DjangoEmail.DoesNotExist:
        raise HTTPException(status_code=404, detail="Email not found")
    if not email.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(email.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("emails_v2", request, jwt, users=users)
    await DjangoEmail.objects.filter(id=item_id).adelete()

@router.put("/emails/{item_id}", response_model=Email)
async def update_item(item_id: str, item: Email, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    i = jsonable_encoder(item)
    try:
        email = await DjangoEmail.objects.select_related('contact').aget(id=item_id)
    except DjangoEmail.DoesNotExist:
        raise HTTPException(status_code=404, detail="Email not found")
    if not email.contact.neomodel_uid:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await get_entry(email.contact.neomodel_uid.hex)
    users = await get_entry_users(entry)
    await authorize_api("emails_v2", request, jwt, users=users)
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
    entry = await get_entry(item.entry)
    users = await get_entry_users(entry)
    await authorize_api("emails_v2", request, jwt, users=users)
    i = item.model_dump()
    try:
        contact = await Contact.objects.aget(neomodel_uid=item.entry)
    except Contact.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Contact {item.entry} not found")
    try:
        email = await DjangoEmail.objects.acreate(
            contact = contact,
            email = item.email,
        )
    except IntegrityError as e:
        logger.debug(f"{e}")
        raise HTTPException(status_code=409, detail=f"L'adresse {item.email} existe déjà pour cette entrée.")

    await email.asave()
    await set_roles(email, item.roles)
    i['id']=email.pk
    return i
