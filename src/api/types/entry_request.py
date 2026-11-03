"""Requests to create or change entries, by name and never by uid.

Uids differ on every backend, so a request refers to things the way people do:
an occupation by its French name, a directory by its name, a person or a place
by what they are called and where. Whether those exist, and which of them a name
refers to, is for preflight (api.serializers.clone.detect); this module only
holds the rules that need no database.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from api.types.effector import RPPS

#: A name longer than this needs a shorter label, and a label may not be longer.
LABEL_MAX = 40


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _blank_is_none(value: str | None) -> str | None:
    return value or None


def check_label(name: str | None, label: str | None) -> None:
    if label is not None and len(label) > LABEL_MAX:
        raise ValueError(f"label is longer than {LABEL_MAX} characters")
    if name is not None and len(name) > LABEL_MAX and not label:
        raise ValueError(f"a name longer than {LABEL_MAX} characters needs a shorter label")


class _Named(_Strict):
    name: str
    label: str | None = None

    _label_blank = field_validator("label")(_blank_is_none)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("name is blank")
        return value

    @model_validator(mode="after")
    def label_fits(self):
        check_label(self.name, self.label)
        return self


class PersonSpec(_Named):
    """A physical person has a gender; an organisation (a service, an association,
    a union) has none."""
    kind: Literal["person", "organisation"]
    gender: Literal["F", "M", "N"] | None = None
    rpps: RPPS | None = None

    @model_validator(mode="after")
    def gender_goes_with_a_person(self):
        if self.kind == "person" and not self.gender:
            raise ValueError("a person needs a gender")
        if self.kind == "organisation" and self.gender:
            raise ValueError("an organisation has no gender")
        return self


class FacilitySpec(_Named):
    """A place. The department then the commune narrow the address search; the
    BAN fields are filled in by the tool that normalises the address."""
    department: str
    commune: str
    building: str | None = None
    street: str | None = None
    geographical_complement: str | None = None
    zip: str | None = None
    ban_id: str | None = None
    ban_banId: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CreateEntryOp(_Strict):
    type: str
    directories: list[str]
    person: PersonSpec
    facility: FacilitySpec
    access: str = "anonymous"

    @field_validator("directories")
    @classmethod
    def at_least_one_directory(cls, value: list[str]) -> list[str]:
        if not [d for d in value if d]:
            raise ValueError("an entry needs at least one of directories")
        return value


class PersonChange(_Strict):
    name: str | None = None
    label: str | None = None
    gender: Literal["F", "M", "N"] | None = None

    _label_blank = field_validator("label")(_blank_is_none)

    @model_validator(mode="after")
    def label_fits(self):
        check_label(self.name, self.label)
        return self


class FacilityChange(_Strict):
    name: str | None = None
    label: str | None = None

    _label_blank = field_validator("label")(_blank_is_none)

    @model_validator(mode="after")
    def label_fits(self):
        check_label(self.name, self.label)
        return self


class DirectoryChange(_Strict):
    add: list[str] = []
    remove: list[str] = []

    @model_validator(mode="after")
    def not_both(self):
        both = sorted(set(self.add) & set(self.remove))
        if both:
            raise ValueError(f"cannot add and remove the same directory: {', '.join(both)}")
        return self


class UpdateEntryOp(_Strict):
    """A change to an existing entry, named by its slug.

    Contacts are not here yet: their shape follows the existing contact
    endpoints and is decided where those are called.
    """
    entry: str
    person: PersonChange | None = None
    facility: FacilityChange | None = None
    directories: DirectoryChange | None = None
    access: str | None = None
    move_to: FacilitySpec | None = None

    @model_validator(mode="after")
    def something_changes(self):
        if not any((self.person, self.facility, self.directories, self.access, self.move_to)):
            raise ValueError("nothing to change")
        return self
