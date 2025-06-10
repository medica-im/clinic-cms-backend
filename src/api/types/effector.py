from __future__ import annotations
from typing import Annotated, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum
from api.types.need import NeedPy
from api.types.situation import SituationPy


class EffectorPost(BaseModel):
    #element_id_property: str = Field(exclude=True)
    name_fr: str
    label_fr: str|None = None
    slug_fr: str|None = None
    gender: Literal['F', 'M', 'N']|None = None


class Effector(EffectorPost):
    uid: str
    name_en: str|None = Field(exclude=True)
    label_en: str|None = Field(exclude=True)
    slug_en: str|None = Field(exclude=True)
    updatedAt: int = 0