from __future__ import annotations
from typing import Annotated, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum
from api.types.need import NeedPy
from api.types.situation import SituationPy
import annotated_types

RPPS = Annotated[int, annotated_types.Ge(10000000000), annotated_types.Le(99999999999)]


class EffectorPost(BaseModel):
    #element_id_property: str = Field(exclude=True)
    name_fr: str
    label_fr: str|None = None
    slug_fr: str|None = None
    gender: Literal['F', 'M', 'N']|None = None
    rpps: RPPS|None = None


class Effector(EffectorPost):
    uid: str
    name_en: str|None = Field(exclude=True)
    label_en: str|None = Field(exclude=True)
    slug_en: str|None = Field(exclude=True)
    updatedAt: int = 0
    createdAt: int = 0


class EffectorPatch(BaseModel):
    name_en: str|None = None
    label_en: str|None = None
    slug_en: str|None = None
    name_fr: str|None = None
    label_fr: str|None = None
    slug_fr: str|None = None
    rpps: RPPS|None = None