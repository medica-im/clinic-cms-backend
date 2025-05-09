from __future__ import annotations
from pydantic import BaseModel, Field
from api.types.website import WebsitePy
from api.types.organization_types import OrganizationTypePy

class OrganizationPy(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None = Field(exclude=True)
    #type: OrganizationTypePy
    #organization: OrganizationPy | None
    #commune: str
    #website: WebsitePy | None
