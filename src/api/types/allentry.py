from pydantic import BaseModel, Field
from typing import Any
from api.types.fullentry import Address, Avatar

class Commune(BaseModel):
    uid: str
    name: str
    slug: str
    wikidata: str


class Department(BaseModel):
    code: str


class EffectorType(BaseModel):
    uid: str
    label: str
    name: str
    slug: str
    definition: str|None = None
    synonyms: list[str]|None = None


class Facility(BaseModel):
    uid: str
    label: str|None = None
    name: str|None = None
    slug: str|None = None


class TagCategory(BaseModel):
    label: str
    labelShort: str
    name: str


class Tag(BaseModel):
    category: TagCategory
    effector_types: list[str]
    label: str
    labelShort: str
    name: str
    uid: str


class Role(BaseModel):
	id: int
	name: str
	label: str
	description: str


class Phone(BaseModel):
    id: int
    type: str
    phone: str
    roles: list[Role]


class Entry(BaseModel):
    address: Address
    avatar: Avatar|None = None
    commune: Commune
    department: Department
    effector_uid: str
    uid: str
    active: bool
    #deactivation_datetime: str|None
    #deactivation_reason: str|None
    updatedAt: int|None = 0
    createdAt: int|None = 0
    facility: Facility
    effector_type: EffectorType
    employers: list[str]|None
    memberships: list[str]|None = None
    gender: str|None = None
    label: str
    name: str
    slug: str
    phones: list[Phone]|None
    tags: list[Tag]