from pydantic import BaseModel, Field
from typing import Any
from api.types.fullentry import Address, Avatar
from api.types.shared import Roles
from api.types.effector_type import Nature

class Commune(BaseModel):
    uid: str
    name: str
    slug: str
    wikidata: str|None=None


class Department(BaseModel):
    code: str


class EffectorType(BaseModel):
    uid: str
    label: str
    raw_label: str|None = None
    name: str
    slug: str
    definition: str|None = None
    synonyms: list[str]|None = None
    nature: Nature|None = None
    immaterial: bool = False


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


class Phone(BaseModel):
    id: int
    type: str
    phone: str
    roles: list[Roles]


class Entry(BaseModel):
    address: Address
    avatar: Avatar|None=None
    commune: Commune
    department: Department
    effector_uid: str
    uid: str
    active: bool|None = None
    #deactivation_datetime: str|None
    #deactivation_reason: str|None
    updatedAt: int|None = 0
    createdAt: int|None = 0
    facility: Facility
    effector_type: EffectorType
    memberships: list[str]|None=None
    gender: str|None=None
    label: str|None=None
    name: str
    slug: str
    entrySlug: str|None=None
    phones: list[Phone]|None=None
    tags: list[Tag]|None=None
    directories: list[str]|None = None
    owner: list[str]|None = None
    creator: list[str]|None = None
    access: str = 'anonymous'
    #: Who the entry is for and how to reach it (directory/facets.py); null is unknown.
    age_min: int|None = None
    age_max: int|None = None
    care_levels: list[str]|None = None
    who_can_contact: str|None = None
    access_modes: list[str]|None = None
    audiences: list[str]|None = None
    free: bool|None = None
    anonymous_care: bool|None = None
