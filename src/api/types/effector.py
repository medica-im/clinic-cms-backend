from __future__ import annotations
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from enum import Enum
from api.types.need import NeedPy
from api.types.situation import SituationPy


class GenderEnum(str, Enum):
    feminine = "F"
    masculine = "M"
    neutral = "N"


class Effector(BaseModel):
    #element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = Field(exclude=True)
    label_fr: str
    label_en: str|None = Field(exclude=True)
    slug_fr: str|None
    slug_en: str|None = Field(exclude=True)
    updatedAt: int = 0
    gender: GenderEnum