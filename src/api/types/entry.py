from pydantic import BaseModel, Field
from typing import Any

class EntryPost(BaseModel):
    effector: str
    effector_type: str
    facility: str
    memberships: list[str]|None
    directory: str|None = None
    isOwner: bool = True
    redeemEmail: str|None = None
    access: str = 'anonymous'


class EntryPatch(BaseModel):
    carte_vitale: bool|None = None
    payment: list[str]|None = None
    third_party_payer: list[str]|None = None
    convention: str|None = None
    active: bool|None = None
    memberships: list[str]|None = None
    owners: list[str]|None = None
    directories: list[str]|None = None
    redeemEmail: str|None = None
    access: str|None = None


class EffectorType(BaseModel):
    uid: str
    label: str
    name: str
    slug: str
    definition: str|None = None
    synonyms: list[str]|None = None


class Entry(BaseModel):
    uid: str
    active: bool
    deactivation_datetime: str|None
    deactivation_reason: str|None
    updatedAt: int = 0
    contactUpdatedAt: int = 0
    createdAt: int|None = 0
    #facility: Any = Field(exclude=True)
    #effector_type: Any = Field(exclude=True)
    #organizations: Any = Field(exclude=True)
    #memberships: Any = Field(exclude=True)
    carte_vitale: bool|None = None
    payment: list[str]|None =None
    third_party_payer: list[str]|None = None
    memberships: list[str]|None = None
    owners: list[str]|None = None
    directories: list[str]|None = None
    redeemEmail: str|None = None
    access: str = 'anonymous'