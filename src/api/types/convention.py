from pydantic import BaseModel, Field

class Convention(BaseModel):
    uid: str
    name: str
    label: str
    definition: str|None