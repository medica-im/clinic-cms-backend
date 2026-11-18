from pydantic import BaseModel
from .shared import Roles


class Phone(BaseModel):
    id: int
    type: str
    phone: str
    roles: list[Roles]


class PhonePost(BaseModel):
    entry: str
    type: str
    phone: str
    roles: list[Roles]
