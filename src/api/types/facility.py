from pydantic import BaseModel, Field, field_validator, model_validator
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
    ban_id: str|None
    ban_banId: str|None

    @field_validator("ban_id", "ban_banId")
    @classmethod
    def blank_ban_id_is_none(cls, value: str|None) -> str|None:
        """The forms send "" when the geocoder was not used; that means no id."""
        return value.strip() or None if value is not None else None


class Facility(FacilityBase):
    uid: str
    commune: Commune
    effectors: list[str]|None
    location: Coordinate|None


class Coordinates(BaseModel):
    """A facility's position: both coordinates, or neither.

    No facility of ours is at 0/0; the forms send that pair when nobody placed
    the facility, so it is stored as no position at all.
    """
    latitude: Decimal|None = None
    longitude: Decimal|None = None

    @model_validator(mode="after")
    def unknown_position_is_none(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be sent together, or both null")
        if self.latitude == 0 and self.longitude == 0:
            self.latitude = None
            self.longitude = None
        return self


class FacilityPost(FacilityBase, Coordinates):
    commune: str


class FacilityPut(FacilityBase, Coordinates):
    pass
