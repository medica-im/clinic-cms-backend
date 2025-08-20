from pydantic import BaseModel

class Phone(BaseModel):
    id: int
    type: str
    phone: str
    roles: list[str]|None = None


class PhonePost(BaseModel):
    entry: str
    type: str
    phone: str
    roles: list[str]|None = None
