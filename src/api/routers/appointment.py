import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import Email as DjangoEmail, Contact
from django.db.utils import DatabaseError
from access.models import Role
from api.types.appointment import Appointment, AppointmentPost
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles
from addressbook.api.serializers import AppointmentSerializer
from directory.utils import appointments_from_neomodel

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/appointments/{item_uid}")
async def delete_item(item_uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("appointments_v2", request, jwt)

@router.post("/appointments/", response_model=Appointment)
async def create_item(item: AppointmentPost, request: Request):
    #await authorize_api("appointments_v2", request, jwt)
    i = item.model_dump()
    serializer = AppointmentSerializer(data=i)
    serializer.is_valid(raise_exception=True):
    appointment_node = serializer.save()
    appointment_dict = appointments_from_neomodel(i["entry"], appointment_node)
    return appointment_dict
    