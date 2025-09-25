from enum import Enum
from pydantic import BaseModel

class Roles(str, Enum):
    ANONYMOUS = 'anonymous'
    STAFF = 'staff'
    ADMINISTRATOR = 'administrator'
    SUPERUSER = 'superuser'


class Role(BaseModel):
    id: int
    name: str
    label: str
    description: str