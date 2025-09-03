from pydantic import BaseModel
from enum import Enum


class Locations(str, Enum):
    HOUSE_CALL = 'house_call'
    OFFICE = 'office'


class Appointment(BaseModel):
    uid: str
    entry: str
    url: str|None = None
    phone: str|None = None
    location: Locations|None = None