from pydantic import BaseModel, Field
from api.types.geography import Commune
from pydantic_extra_types.coordinate import Coordinate

class Facility(BaseModel):
    uid: str
    commune: Commune
    updated: int = 0
    name: str
    label: str|None
    slug: str
    location: Coordinate|None
    zoom: int|None = 18
    building: str|None
    street: str|None  
    geographical_complement: str|None
    zip: str|None