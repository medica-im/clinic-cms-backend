from pydantic import BaseModel, model_validator
from enum import Enum
from typing_extensions import Self


class Locations(str, Enum):
    HOUSE_CALL = 'house_call'
    OFFICE = 'office'


class AppointmentPut(BaseModel):
    entry: str
    url: str|None = None
    phone: str|None = None
    location: Locations|None = None

    @model_validator(mode="after")
    def check_url_phone(self) -> Self:
        if self.url == None and self.phone == None:
            raise ValueError('url field and phone field cannot both be None')
        if self.url and self.phone:
            raise ValueError('url field and phone field cannot both be set')
        return self


class AppointmentPost(AppointmentPut):
    pass


class Appointment(AppointmentPost):
    uid: str

