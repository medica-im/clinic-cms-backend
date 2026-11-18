from __future__ import annotations
from pydantic import BaseModel, Field

class NeedPy(BaseModel):
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    definition_fr: str|None
    definition_en: str|None = Field(exclude=True)
    need: NeedPy|None
