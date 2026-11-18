import re
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# An ICD-11 stem code or block (6A70, 6D11.5, MG30, 6A7), a range of them (6D7-6E0),
# or a chapter number (07). The second character is a letter: F32 is ICD-10.
_STEM = r"[0-9A-Z][A-Z][0-9A-Z]{1,2}(?:\.[0-9A-Z]{1,2})?"
ICD_11 = re.compile(rf"^(?:0[1-9]|1\d|2[0-6]|{_STEM}(?:-{_STEM})?)$")
# DSM-5-TR Section II chapters a condition may sit under. 14 (gender dysphoria) is a
# Situation, 20 and 21 are catch-alls nobody picks, 22 is Situations.
CHAPTERS = frozenset(n for n in range(1, 20) if n != 14)


def _terms(values: list[str]) -> list[str]:
    """Trimmed, empty ones dropped, each term kept once whatever its case."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        term = value.strip()
        if term and term.lower() not in seen:
            seen.add(term.lower())
            out.append(term)
    return out


class ConditionFields(BaseModel):
    name_fr: str
    name_en: str | None = None
    label_fr: str | None = None
    icd_11: list[str] = []
    synonyms_fr: list[str] = []
    synonyms_en: list[str] = []
    kind: Literal["chapter", "condition"] = "condition"
    chapter: int | None = None
    parent: str | None = None
    # "Voir aussi": the situations or conditions it may lead to, by slug.
    may_lead_to: list[str] = []
    # The needs it bears on, by slug.
    impacts: list[str] = []

    @field_validator("may_lead_to", "impacts")
    @classmethod
    def _slugs(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        bad = [v for v in values if not SLUG.match(v)]
        if bad:
            raise ValueError(f"not slugs: {bad}")
        return sorted(set(values))

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name_fr must not be blank")
        return value.strip()

    @field_validator("icd_11")
    @classmethod
    def _icd_11_codes(cls, codes: list[str]) -> list[str]:
        bad = [code for code in codes if not ICD_11.match(code)]
        if bad:
            raise ValueError(f"not ICD-11 codes: {bad}")
        return codes

    @field_validator("synonyms_fr", "synonyms_en")
    @classmethod
    def _synonyms(cls, values: list[str]) -> list[str]:
        return _terms(values)

    @field_validator("chapter")
    @classmethod
    def _a_dsm_chapter(cls, number: int | None) -> int | None:
        if number is not None and number not in CHAPTERS:
            raise ValueError("chapter must be a DSM-5-TR chapter from 1 to 19, except 14")
        return number

    @field_validator("parent")
    @classmethod
    def _parent_is_a_slug(cls, parent: str | None) -> str | None:
        if parent is not None and not SLUG.match(parent):
            raise ValueError("parent must be a slug")
        return parent


class ConditionPost(ConditionFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError("slug is lowercase words joined by hyphens")
        return value

    @model_validator(mode="after")
    def _tree_rules(self):
        if self.parent == self.slug:
            raise ValueError("a condition cannot be its own parent")
        if self.slug in self.may_lead_to:
            raise ValueError("a condition cannot lead to itself")
        if self.kind == "chapter" and self.parent is not None:
            raise ValueError("a chapter has no parent")
        return self


class Condition(ConditionPost):
    uid: str


class ConditionPatch(ConditionFields):
    """Any field may be sent; `model_fields_set` says which were. Sending
    `parent: null` detaches the condition from its parent. The slug is the key
    and cannot be renamed."""
    name_fr: str | None = None
    kind: Literal["chapter", "condition"] | None = None
    icd_11: list[str] | None = None
    synonyms_fr: list[str] | None = None
    synonyms_en: list[str] | None = None
    may_lead_to: list[str] | None = None
    impacts: list[str] | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _no_null_where_a_value_is_required(self):
        for field in ("name_fr", "kind", "icd_11", "synonyms_fr", "synonyms_en", "may_lead_to", "impacts"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("name_fr")
    @classmethod
    def _name_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name_fr must not be blank")
        return value.strip() if value else value

    @field_validator("icd_11")
    @classmethod
    def _icd_11_codes(cls, codes: list[str] | None) -> list[str] | None:
        return None if codes is None else ConditionFields._icd_11_codes(codes)

    @field_validator("synonyms_fr", "synonyms_en")
    @classmethod
    def _synonyms(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _terms(values)


PROPERTIES = ("name_fr", "name_en", "label_fr", "icd_11", "synonyms_fr", "synonyms_en", "kind", "chapter")


def node_properties(condition: ConditionPost) -> dict:
    """What the node stores. The parent and the links are relationships, not properties."""
    properties = {"slug": condition.slug}
    properties.update({name: getattr(condition, name) for name in PROPERTIES})
    return properties


def condition_from_row(node: dict, parent: str | None, may_lead_to=(), impacts=()) -> Condition:
    return Condition(
        may_lead_to=list(may_lead_to),
        impacts=list(impacts),
        uid=node["uid"],
        slug=node["slug"],
        name_fr=node["name_fr"],
        name_en=node.get("name_en"),
        label_fr=node.get("label_fr"),
        icd_11=node.get("icd_11") or [],
        synonyms_fr=node.get("synonyms_fr") or [],
        synonyms_en=node.get("synonyms_en") or [],
        kind=node.get("kind") or "condition",
        chapter=node.get("chapter"),
        parent=parent,
    )
