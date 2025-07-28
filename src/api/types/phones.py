from pydantic import BaseModel

class Phone(BaseModel):
    id: int
    type: str
    phone: str