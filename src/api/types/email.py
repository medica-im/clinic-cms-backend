from pydantic import BaseModel
from enum import Enum

class Roles(str, Enum):
    ANONYMOUS = 'anonymous'
    STAFF = 'staff'
    ADMINISTRATOR = 'administrator'
    SUPERUSER = 'superuser'


class Email(BaseModel):
    id: int
    email: str
    roles: list[Roles]|None = None


class EmailPost(BaseModel):
    entry: str
    email: str
    roles: list[Roles]|None = None
