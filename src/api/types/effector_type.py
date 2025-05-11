from __future__ import annotations
from pydantic import BaseModel, Field
from api.types.need import NeedPy
from api.types.situation import SituationPy

class EffectorTypePy(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None = Field(exclude=True)
    definition_fr: str|None
    definition_en: str|None = Field(exclude=True)
    slug_en: str|None
    slug_fr: str|None = Field(exclude=True)
    effector_type: EffectorTypePy|None
    need: list[NeedPy]|None
    situation: list[SituationPy]|None