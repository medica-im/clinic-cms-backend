from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, model_validator

from api.types.condition import SLUG, _terms
from api.types.need import NeedPy

class SituationPy(BaseModel):
    uid: str
    name_en: str|None = Field(exclude=True)
    name_fr: str
    definition_en: str|None = Field(exclude=True)
    definition_fr: str|None
    ICD_11: list[str]|None
    need: list[NeedPy]|None


class Situation(BaseModel):
    uid: str
    name: str
    entries: list[str]


def _slugs(values: list[str], field: str) -> list[str]:
    bad = [value for value in values if not SLUG.match(value)]
    if bad:
        raise ValueError(f"{field} must be slugs: {bad}")
    return sorted(set(values))


class SituationFields(BaseModel):
    """A node of the situations tree. `parent` is its PART_OF, `may_lead_to` the
    situations it can lead to (the "voir aussi" of /concerns), `impacts` the Needs
    it bears on; all three by slug."""
    name_fr: str
    name_en: str | None = None
    definition_fr: str | None = None
    definition_en: str | None = None
    synonyms_fr: list[str] = []
    synonyms_en: list[str] = []
    parent: str | None = None
    may_lead_to: list[str] = []
    impacts: list[str] = []

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name_fr must not be blank")
        return value.strip()

    @field_validator("synonyms_fr", "synonyms_en")
    @classmethod
    def _synonyms(cls, values: list[str]) -> list[str]:
        return _terms(values)

    @field_validator("parent")
    @classmethod
    def _parent_is_a_slug(cls, parent: str | None) -> str | None:
        if parent is not None and not SLUG.match(parent):
            raise ValueError("parent must be a slug")
        return parent

    @field_validator("may_lead_to", "impacts")
    @classmethod
    def _targets_are_slugs(cls, values: list[str], info) -> list[str]:
        return _slugs(values, info.field_name)


class SituationPost(SituationFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError("slug is lowercase words joined by hyphens")
        return value

    @model_validator(mode="after")
    def _not_its_own_target(self):
        if self.parent == self.slug:
            raise ValueError("a situation cannot be its own parent")
        if self.slug in self.may_lead_to:
            raise ValueError("a situation cannot lead to itself")
        return self


class SituationNode(SituationFields):
    """What the API returns. A node that predates the slug has none, and is told
    apart by its uid until PATCH /situations/by-uid/{uid} gives it one."""
    uid: str
    slug: str | None = None
    #: The same links by uid, so that a node with no slug can still be followed.
    parent_uid: str | None = None
    parent_uids: list[str] = []
    may_lead_to_uids: list[str] = []
    impacts_uids: list[str] = []


class SlugBody(BaseModel):
    """The one thing PATCH .../by-uid/{uid} takes."""
    slug: str

    model_config = {"extra": "forbid"}

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError("slug is lowercase words joined by hyphens")
        return value


class SituationPatch(SituationFields):
    """Any field may be sent; `model_fields_set` says which were. `parent: null`
    detaches the situation; a list replaces the edges it names, `[]` clears them.
    The slug is the key and cannot be renamed."""
    name_fr: str | None = None
    synonyms_fr: list[str] | None = None
    synonyms_en: list[str] | None = None
    may_lead_to: list[str] | None = None
    impacts: list[str] | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _no_null_where_a_value_is_required(self):
        for field in ("name_fr", "synonyms_fr", "synonyms_en", "may_lead_to", "impacts"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else SituationFields._name_is_not_blank(value)

    @field_validator("synonyms_fr", "synonyms_en")
    @classmethod
    def _synonyms(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _terms(values)

    @field_validator("may_lead_to", "impacts")
    @classmethod
    def _targets_are_slugs(cls, values: list[str] | None, info) -> list[str] | None:
        return None if values is None else _slugs(values, info.field_name)


SITUATION_PROPERTIES = ("name_fr", "name_en", "definition_fr", "definition_en", "synonyms_fr", "synonyms_en")


def situation_from_row(row: dict) -> SituationNode:
    node = row["s"]
    return SituationNode(
        uid=node["uid"],
        slug=node.get("slug"),
        name_fr=node["name_fr"],
        name_en=node.get("name_en"),
        definition_fr=node.get("definition_fr"),
        definition_en=node.get("definition_en"),
        synonyms_fr=node.get("synonyms_fr") or [],
        synonyms_en=node.get("synonyms_en") or [],
        parent=row["parent"],
        may_lead_to=row["may_lead_to"],
        impacts=row["impacts"],
        parent_uid=row["parent_uid"],
        parent_uids=row["parent_uids"],
        may_lead_to_uids=row["may_lead_to_uids"],
        impacts_uids=row["impacts_uids"],
    )
