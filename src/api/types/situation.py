from __future__ import annotations
from pydantic import BaseModel, Field

from api.types.need import NeedPy

class SituationPy(BaseModel):
    uid: str
    name_en: str|None = Field(exclude=True)
    name_fr: str
    definition_en: str|None = Field(exclude=True)
    definition_fr: str|None
    ICD_11: list[str]|None
    need: list[NeedPy]|None
