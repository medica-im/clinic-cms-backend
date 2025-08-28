
from pydantic import BaseModel, Field
from typing import Any

class EntryPost(BaseModel):
    effector: str
    effector_type: str
    facility: str
    organizations: list[str]|None


class EntryPatch(BaseModel):
    carte_vitale: bool|None = None


class Entry(BaseModel):
    uid: str
    active: bool
    deactivation_datetime: str|None
    deactivation_reason: str|None
    updatedAt: int = 0
    contactUpdatedAt: int = 0
    #effector: Any = Field(exclude=True)
    #facility: Any = Field(exclude=True)
    #effector_type: Any = Field(exclude=True)
    #organizations: Any = Field(exclude=True)
    #memberships: Any = Field(exclude=True)
    carte_vitale: bool|None = None