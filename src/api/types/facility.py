from pydantic import BaseModel, Field
from api.types.geography import Commune
from pydantic_extra_types.coordinate import Coordinate
from decimal import Decimal

class FacilityBase(BaseModel):
    updated: int|None = 0
    name: str|None
    label: str|None
    slug: str|None
    zoom: int|None = 18
    building: str|None
    street: str|None
    geographical_complement: str|None
    zip: str|None


class Facility(FacilityBase):
    uid: str
    commune: Commune
    effectors: list[str]|None
    location: Coordinate|None


class FacilityPost(FacilityBase):
    commune: str
    ban_id: str
    ban_banId: str
    latitude: Decimal|None = None
    longitude: Decimal|None = None
