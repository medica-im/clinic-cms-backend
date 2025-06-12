
from pydantic import BaseModel, Field

class EntryPost(BaseModel):
    effector: str
    effector_type: str
    facility: str