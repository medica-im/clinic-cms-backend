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

@router.delete("/appointments/{item_uid}")
async def delete_item(item_uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("appointments_v2", request, jwt)
