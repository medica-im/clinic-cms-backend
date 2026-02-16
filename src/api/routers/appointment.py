import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
import jwt
from addressbook.models import Email as DjangoEmail, Contact
from django.db.utils import DatabaseError
from access.models import Role
from directory.models.agraph import Appointment as AgraphAppointment
from api.types.appointment import Appointment, AppointmentPost, AppointmentPut
from api.auth import JWT
from api.auth import authorize_api
from api.serializers.appointment import AppointmentSerializer
from directory.utils import appointments_from_neomodel
from neomodel import adb
from neomodel.exceptions import CardinalityViolation

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/appointments/", response_model=Appointment)
async def create_item(item: AppointmentPost, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("appointments_v2", request, jwt)
    i = item.model_dump()
    serializer = AppointmentSerializer(data=i)
    serializer.is_valid(raise_exception=True)
    appointment_node = serializer.save()
    appointment_dict = appointments_from_neomodel(i["entry"], appointment_node)
    return appointment_dict[0] # type: ignore

@router.put("/appointments/{item_uid}", response_model=Appointment)
async def update_item(item_uid: str, item: AppointmentPut, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        instance = await AgraphAppointment.nodes.get(uid=item_uid)
    except AgraphAppointment.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Appointment not found")
    try:
        entry_node = await instance.entry.single()
    except CardinalityViolation:
        raise HTTPException(status_code=500, detail=f"Entry associated with Appointment {item_uid} not found")
    users = await entry_node.owner.all() or await entry_node.creator.all()
    await authorize_api("appointments_v2", request, jwt, users)
    i = item.model_dump()
    serializer = AppointmentSerializer(instance, data=i)
    serializer.is_valid(raise_exception=True)
    appointment_node = serializer.save()
    appointment_dict = appointments_from_neomodel(i["entry"], appointment_node)
    return appointment_dict[0] # type: ignore

@router.delete("/appointments/{item_uid}")
async def delete_item(item_uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        instance = await AgraphAppointment.nodes.get(uid=item_uid)
    except AgraphAppointment.DoesNotExist:
        raise HTTPException(status_code=404, detail="Appointment not found")
    try:
        entry_node = await instance.entry.single()
    except CardinalityViolation:
        raise HTTPException(status_code=500, detail=f"Entry associated with Appointment {item_uid} not found")
    users = await entry_node.owner.all() or await entry_node.creator.all()
    await authorize_api("appointments_v2", request, jwt, users)
    await instance.delete()
