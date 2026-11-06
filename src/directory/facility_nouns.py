"""Place words for the facility address (EffectorType.facility_noun_fr).

The word is inherited through IS_A (directory/facility_slug.py, PLACE_WORD), so
it is set on the parent where every child shares it: "médecin" carries
"cabinet médical" and the specialists below it inherit it. A type that differs
from its parent carries its own.

Types are keyed by name_fr: a uid is unique per Neo4j server only. A type that
does not exist on a backend is reported and skipped.
"""
from dataclasses import dataclass, field

from neomodel import adb

FACILITY_NOUNS: dict[str, str] = {
    "médecin": "cabinet médical",
    "radiologue": "cabinet de radiologie",
    "médecin biologiste": "laboratoire d'analyses médicales",
    "pharmacien biologiste": "laboratoire d'analyses médicales",
    "kinésithérapeute": "cabinet de kinésithérapie",
    "diététicien": "cabinet de diététique",
    "infirmière": "cabinet infirmier",
    "sage-femme": "cabinet de sage-femme",
    "orthophoniste": "cabinet d'orthophonie",
    "orthoptiste": "cabinet d'orthoptie",
    "dentiste": "cabinet dentaire",
    "psychologue": "cabinet de psychologie",
    "psychomotricien": "cabinet de psychomotricité",
    "pédicure-podologue": "cabinet de podologie",
    "ergothérapeute": "cabinet d'ergothérapie",
    "ostéopathe": "cabinet d'ostéopathie",
    "sophrologue": "cabinet de sophrologie",
    "psychopraticien": "cabinet de psychothérapie",
    "sexothérapeute": "cabinet de sexothérapie",
    "pharmacien": "pharmacie",
}

TYPES = "MATCH (t:EffectorType) WHERE t.name_fr IN $names RETURN t.uid, t.name_fr, t.facility_noun_fr"
WRITE = "MATCH (t:EffectorType {uid: $uid}) SET t.facility_noun_fr = $noun"


@dataclass
class NounChange:
    uid: str
    name_fr: str
    old: str | None
    new: str


@dataclass
class NounPlan:
    #: types with no word yet: the only ones the seed writes
    changes: list[NounChange] = field(default_factory=list)
    #: types that already carry another word: left to whoever chose it
    kept: list[NounChange] = field(default_factory=list)
    #: names from the table that this backend does not have
    missing: list[str] = field(default_factory=list)


async def plan_facility_nouns(nouns: dict[str, str] = FACILITY_NOUNS) -> NounPlan:
    rows, _ = await adb.cypher_query(TYPES, {"names": list(nouns)})
    plan = NounPlan()
    found = set()
    for uid, name_fr, old in sorted(rows, key=lambda r: r[1]):
        found.add(name_fr)
        change = NounChange(uid, name_fr, old or None, nouns[name_fr])
        if not change.old:
            plan.changes.append(change)
        elif change.old != change.new:
            plan.kept.append(change)
    plan.missing = [n for n in nouns if n not in found]
    return plan


async def apply_facility_nouns(plan: NounPlan) -> None:
    for c in plan.changes:
        await adb.cypher_query(WRITE, {"uid": c.uid, "noun": c.new})
