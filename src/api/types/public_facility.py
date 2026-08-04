from decimal import Decimal
from pydantic import BaseModel
from api.types.shared import Role


class Address(BaseModel):
    facility_uid: str
    country: str
    city: str | None = None
    zip: str | None = None
    geographical_complement: str | None = None
    street: str | None = None
    building: str | None = None
    longitude: Decimal | None = None
    latitude: Decimal | None = None
    zoom: int | None = None
    tooltip_direction: str | None = None
    tooltip_permanent: bool | None = None


class PhonePublic(BaseModel):
    id: int
    phone: str
    type: str
    type_display: str
    roles: list[Role]


class EmailPublic(BaseModel):
    id: int
    email: str
    roles: list[Role]


class WebsitePublic(BaseModel):
    id: int
    url: str
    roles: list[Role]


class SocialNetworkPublic(BaseModel):
    id: int
    type: str
    type_display: str
    handle: str | None = None
    url: str
    roles: list[Role]


class Avatar(BaseModel):
    sm: str | None = None
    lg: str | None = None
    raw: str | None = None


class PlaceImage(BaseModel):
    """
    A wide (16:9) photograph of the place, as opposed to the square avatar.

    Carries no access level: unlike a person's picture, a photograph of a
    building is public.
    """
    sm: str | None = None
    lg: str | None = None
    raw: str | None = None
    alt: str = ""


class PublicFacility(BaseModel):
    uid: str
    name: str | None = None
    label: str | None = None
    slug: str | None = None
    commune: str | None = None
    address: Address
    organizations: list[str]
    phones: list[PhonePublic] | None = None
    emails: list[EmailPublic] | None = None
    websites: list[WebsitePublic] | None = None
    socialnetworks: list[SocialNetworkPublic] | None = None
    avatar: Avatar | None = None
    image: PlaceImage | None = None
    entries: list[str]
    ban_id: str | None = None
    ban_banId: str | None = None
