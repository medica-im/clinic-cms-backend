import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import Email as DjangoEmail, Contact
from django.db.utils import DatabaseError
from access.models import Role
from directory.models.graph import Appointment as GraphAppointment
from api.types.appointment import Appointment, AppointmentPost, AppointmentPut
from api.auth import JWT
from api.auth import authorize_api
from api.utils import set_roles
from api.serializers.appointment import AppointmentSerializer
from directory.utils import appointments_from_neomodel
from neomodel import db

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/appointments/", response_model=Appointment)
async def create_item(item: AppointmentPost, request: Request):
    #await authorize_api("appointments_v2", request, jwt)
    i = item.model_dump()
    serializer = AppointmentSerializer(data=i)
    serializer.is_valid(raise_exception=True)
    appointment_node = serializer.save()
    appointment_dict = appointments_from_neomodel(i["entry"], appointment_node)
    return appointment_dict[0] # type: ignore

@router.put("/appointments/{item_uid}", response_model=Appointment)
async def update_item(item_uid: str, item: AppointmentPut, request: Request):
    #await authorize_api("appointments_v2", request, jwt)
    i = item.model_dump()
    instance = GraphAppointment.nodes.get(uid=item_uid)
    serializer = AppointmentSerializer(instance, data=i)
    serializer.is_valid(raise_exception=True)
    appointment_node = serializer.save()
    appointment_dict = appointments_from_neomodel(i["entry"], appointment_node)
    return appointment_dict[0] # type: ignore

@router.delete("/appointments/{item_uid}", response_model=Appointment)
async def delete_item(item_uid: str, request: Request):
    #await authorize_api("appointments_v2", request, jwt)
    query = f"""MATCH(n:Appointment) WHERE n.uid="{item_uid}" DETACH DELETE n"""
    db.cypher_query(query)
