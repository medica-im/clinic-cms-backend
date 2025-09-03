from pydantic import BaseModel
from enum import Enum


class Locations(str, Enum):
    HOUSE_CALL = 'house_call'
    OFFICE = 'office'


class AppointmentPost(BaseModel):
    entry: str
    url: str|None = None
    phone: str|None = None
    location: Locations|None = None


class Appointment(AppointmentPost):
    uid: str