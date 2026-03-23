from __future__ import annotations
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from api.types.need import NeedPy
from api.types.situation import SituationPy


class EffectorTypePost(BaseModel):
    name_fr: str
    name_en: str|None = None
    label_fr: str
    label_en: str|None = None
    slug_fr: str
    slug_en: str|None = None
    synonyms_fr: list[str]|None = None
    synonyms_en: list[str]|None = None
    definition_fr: str|None = None
    definition_en: str|None = None
    isHCW: bool = False
    concept_fr: str|None = None
    concept_en: str|None = None
    unique_ID: str|None = None
    isRPPS: bool = False
    effector_type_uid: str|None = None


class EffectorTypePatch(BaseModel):
    name_fr: str|None = None
    name_en: str|None = None
    label_fr: str|None = None
    label_en: str|None = None
    slug_fr: str|None = None
    slug_en: str|None = None
    synonyms_fr: list[str]|None = None
    synonyms_en: list[str]|None = None
    definition_fr: str|None = None
    definition_en: str|None = None
    isHCW: bool|None = None
    concept_fr: str|None = None
    concept_en: str|None = None
    unique_ID: str|None = None
    isRPPS: bool|None = None
    effector_type_uid: str|None = None


class EffectorType(BaseModel):
    element_id_property: str = Field(exclude=True)
    uid: str
    name_fr: str
    name_en: str|None = None
    label_fr: str
    label_en: str|None = None
    synonyms_fr: list[str]|None
    synonyms_en: list[str]|None = None
    definition_fr: str|None
    definition_en: str|None = None
    slug_fr: str|None
    slug_en: str|None = None
    effector_type: Annotated[EffectorType|None, Field(exclude=True)] = None
    effector_type_uid: str|None = None
    effector_type_label_fr: str|None = None
    isHCW: bool = False
    isRPPS: bool = False
    need: Annotated[list[NeedPy]|None, Field(exclude=True)] = None
    situation: Annotated[list[SituationPy]|None, Field(exclude=True)] = None
    concept_fr: str|None = None
    concept_en: str|None = None
    unique_ID: str|None = None