from pydantic import BaseModel
from .shared import Roles


class Email(BaseModel):
    id: int
    email: str
    roles: list[Roles]|None = None


class EmailPost(BaseModel):
    entry: str
    email: str
    roles: list[Roles]|None = None
