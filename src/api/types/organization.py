from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any
from django.conf import settings
from api.types.website import WebsitePy
from api.types.organization_types import OrganizationTypePy
from api.types.geography import Commune
from api.types.fullentry import Address


class OrganizationAddress(Address):
    public_holidays_zone: str|None = None


class OrganizationPy(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    type: OrganizationTypePy
    organization: OrganizationPy | None
    commune: Commune
    website: WebsitePy | None

class Contact(BaseModel):
    id: int
    formatted_name: str
    formatted_name_definite_article: str
    url: str
    address: OrganizationAddress
    phonenumbers: list[Any]
    socialnetworks: list[Any]
    websites: list[Any]
    emails: list[Any]


class Category(BaseModel):
    id: int
    name: str
    formatted_name: str
    definition: str
    slug: str

class LegalEntity(BaseModel):
    id: int
    name: str|None
    type: str|None
    get_type_display: str|None
    RNA: str|None
    SIREN: str|None
    SIRET: str|None
    RCS: str|None
    SHARE_CAPITAL: str|None
    VAT: str|None


class Gender(BaseModel):
    id: int
    name: str
    label: str
    label_fr: str
    label_en: str
    code: str


class City(BaseModel):
    id: int
    name: str
    label: str
    label_fr: str|None = None
    label_en: str|None=None
    to_label: str|None=None
    to_label_fr: str|None=None
    to_label_en: str|None=None
    from_label: str|None=None
    from_label_fr: str|None=None
    from_label_en: str|None=None
    grammatical_number: str|None


class Department(BaseModel):
    uid: str
    name: str
    code: str
    slug: str
    wikidata: str


class Organization(BaseModel):
    id: int
    uid: str
    name: str
    company_name: str
    language: str
    formatted_name: str
    formatted_name_short: str
    formatted_name_definite_article: str
    website_title: str
    website_description: str
    category: Category
    contact: Contact
    registration: bool
    google_site_verification: str
    google_calendar_id: str|None=None
    google_calendar_api_key: str|None=None
    city: City|None = None
    commune: Commune|None = None
    gender: Gender|None=None
    legal_entity: LegalEntity
    department: Department
    timezone: str = settings.TIME_ZONE
    logo: str|None
    logo_alt: str|None
    sandbox: bool = False