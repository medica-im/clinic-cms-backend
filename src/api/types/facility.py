from pydantic import BaseModel, Field
from api.types.geography import Commune
from pydantic_extra_types.coordinate import Coordinate

class FacilityBase(BaseModel):
    uid: str
    updated: int = 0
    name: str|None
    label: str|None
    slug: str|None
    location: Coordinate|None
    zoom: int|None = 18
    building: str|None
    street: str|None  
    geographical_complement: str|None
    zip: str|None


class Facility(FacilityBase):
    commune: Commune
    effectors: list[str]|None


class FacilityCreate(FacilityBase):
    commune: str