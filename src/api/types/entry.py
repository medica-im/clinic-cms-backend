import re

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any
from directory.facets import (
    ACCESS_MODES,
    AUDIENCES,
    CARE_LEVELS,
    WHO_CAN_CONTACT,
    check_age_range,
    check_choice,
    check_choices,
)
from directory.identifiers import is_siren, normalize


class EntryFacets(BaseModel):
    """Who the entry is for and how to reach it. Null is unknown, never "no"; see directory/facets.py."""
    age_min: int|None = None
    age_max: int|None = None
    care_levels: list[str]|None = None
    who_can_contact: str|None = None
    access_modes: list[str]|None = None
    audiences: list[str]|None = None
    free: bool|None = None
    anonymous_care: bool|None = None

    @field_validator("age_min", "age_max")
    @classmethod
    def _whole_years(cls, value):
        return check_age_range(value, None)[0]

    @field_validator("care_levels")
    @classmethod
    def _care_levels(cls, value):
        return check_choices(value, CARE_LEVELS, "care_levels")

    @field_validator("who_can_contact")
    @classmethod
    def _who_can_contact(cls, value):
        return check_choice(value, WHO_CAN_CONTACT, "who_can_contact")

    @field_validator("access_modes")
    @classmethod
    def _access_modes(cls, value):
        return check_choices(value, ACCESS_MODES, "access_modes")

    @field_validator("audiences")
    @classmethod
    def _audiences(cls, value):
        return check_choices(value, AUDIENCES, "audiences")

    @model_validator(mode="after")
    def _age_range(self):
        check_age_range(self.age_min, self.age_max)
        return self



def a_siren_or_nothing(value: str|None) -> str|None:
    """The number without its spaces, or a refusal: 9 digits, ending in the right check digit."""
    siren = normalize(value)
    if siren is not None and not is_siren(siren):
        raise ValueError("not a SIREN: 9 digits, ending in the right check digit")
    return siren

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def slugs_or_nothing(values: list[str]|None) -> list[str]|None:
    """The list unchanged, or a refusal naming a word that is not a slug."""
    if values is not None:
        bad = [value for value in values if not SLUG.match(value)]
        if bad:
            raise ValueError(f"not slugs: {bad}")
    return values


class EntryPost(EntryFacets):
    effector: str
    effector_type: str
    facility: str
    memberships: list[str]|None
    directory: str|None = None
    isOwner: bool = True
    redeemEmail: str|None = None
    access: str = 'anonymous'
    #: The address of a facility that has none yet; see assign_facility_slug.
    facility_slug: str|None = None
    #: The uid of the entry that runs this one (RUN_BY); administrators and superusers only.
    run_by: str|None = None
    #: The SIREN of the legal unit this entry is (a porteur's); administrators and superusers only.
    siren: str|None = None
    #: The slugs of the conditions, situations and needs this entry handles (MANAGES).
    manages: list[str]|None = None
    #: The uids of the places this entry answers for (COVERS): communes, departments, regions, the country.
    coverage: list[str]|None = None

    _siren = field_validator("siren")(a_siren_or_nothing)
    _manages = field_validator("manages")(slugs_or_nothing)


class EntryPatch(EntryFacets):
    carte_vitale: bool|None = None
    payment: list[str]|None = None
    third_party_payer: list[str]|None = None
    convention: str|None = None
    active: bool|None = None
    memberships: list[str]|None = None
    owners: list[str]|None = None
    directories: list[str]|None = None
    redeemEmail: str|None = None
    access: str|None = None
    #: Sent as null, detaches the entry from its porteur; left out, leaves it alone.
    run_by: str|None = None
    #: Sent as null, removes the SIREN; left out, leaves it alone.
    siren: str|None = None
    #: Replaces what the entry manages; sent as null or empty, clears it; left out, leaves it alone.
    manages: list[str]|None = None
    #: Replaces the places the entry answers for; sent as null or empty, clears them; left out, leaves them alone.
    coverage: list[str]|None = None

    _siren = field_validator("siren")(a_siren_or_nothing)
    _manages = field_validator("manages")(slugs_or_nothing)


class EffectorType(BaseModel):
    uid: str
    label: str
    name: str
    slug: str
    definition: str|None = None
    synonyms: list[str]|None = None


class Entry(EntryFacets):
    uid: str
    active: bool
    deactivation_datetime: str|None
    deactivation_reason: str|None
    updatedAt: int = 0
    contactUpdatedAt: int = 0
    createdAt: int|None = 0
    #facility: Any = Field(exclude=True)
    #effector_type: Any = Field(exclude=True)
    #organizations: Any = Field(exclude=True)
    #memberships: Any = Field(exclude=True)
    carte_vitale: bool|None = None
    payment: list[str]|None =None
    third_party_payer: list[str]|None = None
    memberships: list[str]|None = None
    owners: list[str]|None = None
    directories: list[str]|None = None
    redeemEmail: str|None = None
    access: str = 'anonymous'
    #: The uid of the entry that runs this one, if any.
    run_by: str|None = None
    #: The SIREN of the legal unit this entry is, if it is one.
    siren: str|None = None
    #: The slugs of what this entry manages, as set on the entry itself.
    manages: list[str]|None = None
    #: The uids of the places it answers for, as set on the entry itself.
    coverage: list[str]|None = None
