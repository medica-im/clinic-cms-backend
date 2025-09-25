from pydantic import BaseModel, Field, NonNegativeInt
from typing import Any
from decimal import Decimal
from api.types.appointment import Appointment
from api.types.convention import Convention
from api.types.shared import Role
from api.types.payment_method import PaymentMethod
from api.types.third_party_payer import ThirdPartyPayer
from enum import Enum
from api.types.effector import RPPS

class EntryPost(BaseModel):
    effector: str
    effector_type: str
    facility: str
    organizations: list[str]|None


class EntryPatch(BaseModel):
    carte_vitale: bool|None = None
    payment: list[str]|None = None
    third_party_payer: list[str]|None = None
    convention: str|None = None


class Address(BaseModel):
    building: str|None = None
    city: str
    country: str
    facility_uid: str
    geographical_complement: str|None = None
    latitude: Decimal|None = None
    longitude: Decimal|None = None
    street: str
    tooltip_direction: str|None = None
    tooltip_text: str|None = None
    tooltip_permanent: bool|None = None
    zip: str|None = None
    zoom: NonNegativeInt|None = None


class Avatar(BaseModel):
    fb: str
    lt: str
    raw: str


class EffectorType(BaseModel):
    definition: str|None = None
    label: str
    labels: list[str]
    name: str
    slug: str
    synonyms: list[str]|None = None
    uid: str


class Email(BaseModel):
    id: int
    email: str
    roles: list[Role]|None = None


class Facility(BaseModel):
    uid: str
    name: str
    label: str
    slug: str


class Contact(BaseModel):
        id: int
        blurb: str|None = None
        first_name: str
        formatted_name: str
        formatted_name_definite_article: str
        id: int
        last_name: str
        middle_name: str
        neomodel_uid: str
        organization: str
        person_type: str
        profile_image: str
        qr_image: str
        title: str
        twitter_handle: str|None = None
        url: str
        user: str|None = None
        worked_with: list[Any]

class PhoneType(str, Enum):
    MOBILE = 'M'
    MOBILE_WORK = 'MW'
    WORK = 'W'
    FAX = 'F'
    ANSWERING_SERVICE = 'AS'


class Phone(BaseModel):
    id: int
    contact: Contact
    phone: str
    type: PhoneType
    type_display: str
    roles: list[Role]|None = None

    class Config:  
        use_enum_values = True


class SocialNetwork(BaseModel):
    id: int
    handle: str
    url: str
    type: str
    type_display: str


class Website(BaseModel):
    id: int
    roles: list[Role]
    url: str


class FullEntry(BaseModel):
    active: bool
    address: Address
    appointments: list[Appointment]
    avatar: Avatar
    carte_vitale: bool|None = None
    convention: Convention|None = None
    deactivation_datetime: str|None
    deactivation_reason: str|None
    effector_uid: str
    emails: list[Email]|None = None
    facility: Facility
    label: str
    name: str
    contactUpdatedAt: int = 0
    effector_type: EffectorType
    #organizations: Any = Field(exclude=True)
    #memberships: Any = Field(exclude=True)
    payment_methods: list[PaymentMethod]|None = None
    phones: list[Phone]|None = None
    profile: str|None = None
    rpps: RPPS|None = None
    slug: str
    socialnetworks: list[SocialNetwork]
    spoken_languages: list[str]
    third_party_payers: list[ThirdPartyPayer]|None = None
    uid: str
    updatedAt: int = 0
    websites: list[Website]
    organizations: list[str]|None = None
    memberships: list[str]|None = None