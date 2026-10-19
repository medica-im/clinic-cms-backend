from __future__ import annotations
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field
from api.types.need import NeedPy
from api.types.situation import SituationPy

# What an entry of the type does: a profession is practised by a person, so its
# label agrees with that person's grammatical gender; a service or an activity
# has one form whoever the effector is.
Nature = Literal["profession", "service", "activity"]


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
    # False: a category that only groups other types; entries never have it.
    assignable: bool = True
    nature: Nature|None = None


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
    assignable: bool|None = None
    nature: Nature|None = None


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
    assignable: bool = True
    nature: Nature|None = None
    need: Annotated[list[NeedPy]|None, Field(exclude=True)] = None
    situation: Annotated[list[SituationPy]|None, Field(exclude=True)] = None
    concept_fr: str|None = None
    concept_en: str|None = None
    unique_ID: str|None = None