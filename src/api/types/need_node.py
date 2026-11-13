"""The Need API's bodies. `need.py` holds the legacy nested shape the situations
listing uses; these are the flat ones the console edits, the parents by slug.

Needs form a graph, not a tree: Henderson's housing serves warmth, hygiene and
sleep alike, so a need has a list of parents (never a loop)."""
from pydantic import BaseModel, field_validator, model_validator

from api.types.condition import SLUG


class NeedFields(BaseModel):
    name_fr: str
    name_en: str | None = None
    definition_fr: str | None = None
    definition_en: str | None = None
    parents: list[str] = []

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name_fr must not be blank")
        return value.strip()

    @field_validator("parents")
    @classmethod
    def _parents_are_slugs(cls, parents: list[str]) -> list[str]:
        bad = [p for p in parents if not SLUG.match(p)]
        if bad:
            raise ValueError(f"parents must be slugs: {bad}")
        return sorted(set(parents))


class NeedPost(NeedFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError("slug is lowercase words joined by hyphens")
        return value

    @model_validator(mode="after")
    def _not_its_own_parent(self):
        if self.slug in self.parents:
            raise ValueError("a need cannot be its own parent")
        return self


class NeedNode(NeedFields):
    """What the API returns. A node that predates the slug has none, and is told
    apart by its uid until PATCH /needs/by-uid/{uid} gives it one."""
    uid: str
    slug: str | None = None
    #: The parents by uid too, so that a node with no slug can still be followed.
    parent_uids: list[str] = []


class NeedPatch(NeedFields):
    """Any field may be sent; `model_fields_set` says which were. `parents`
    replaces every parent, `[]` detaches the need. The slug is the key and cannot
    be renamed."""
    name_fr: str | None = None
    parents: list[str] | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _no_null_where_a_value_is_required(self):
        for field in ("name_fr", "parents"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("parents")
    @classmethod
    def _parents_are_slugs(cls, parents: list[str] | None) -> list[str] | None:
        return None if parents is None else NeedFields._parents_are_slugs(parents)

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else NeedFields._name_is_not_blank(value)


NEED_PROPERTIES = ("name_fr", "name_en", "definition_fr", "definition_en")


def need_from_row(row: dict) -> NeedNode:
    node = row["n"]
    return NeedNode(
        uid=node["uid"],
        slug=node.get("slug"),
        name_fr=node["name_fr"],
        name_en=node.get("name_en"),
        definition_fr=node.get("definition_fr"),
        definition_en=node.get("definition_en"),
        parents=row["parents"],
        parent_uids=row["parent_uids"],
    )
