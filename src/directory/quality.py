"""Quality controls of the directory: what an entry must say, by what it is and what it offers.

A ligne d'écoute without a phone number is a line nobody can call. It went unnoticed: the import
had dropped the number and nothing looked for it. These rules look.

Every rule is a warning, never a refusal to save: an entry is created in steps, and a partial
entry is worth more than none. `problems()` is a pure function of `EntryFacts` so each rule is
tested without a database; `entry_facts` and `directory_facts` gather the facts. An entry that is
not listed, or not active, is not judged, except for the rules about being a porteur: the
porteurs are unlisted on purpose.
"""
import re
from dataclasses import dataclass, field
from typing import Callable

from api.graph import read

#: What the page can word: « missing » is a gap a reader hits at once (nobody can call, nothing on
#: the map); « incomplete » is information the entry could add.
SEVERITIES = ("missing", "incomplete")


@dataclass
class EntryFacts:
    """Everything a rule reads about one entry, gathered once."""

    uid: str
    slug: str | None
    name: str
    label: str | None
    type_slug: str
    immaterial: bool
    nature: str | None
    listed: bool
    active: bool
    description: str | None
    offers: list[str] | None
    who_can_contact: str | None
    care_levels: list[str] | None
    siren: str | None
    has_porteur: bool
    #: How many places the entry covers (COVERS).
    coverage: int
    #: The channels of its schedules ("on_site", "phone", ...).
    schedules: list[str]
    #: A street and a point on the map.
    has_location: bool
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    access_modes: list[str] | None = None


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    #: True when the entry breaks the rule.
    broken: Callable[[EntryFacts], bool]
    #: Judged even when the entry is not listed (the rules about being a porteur).
    unlisted_too: bool = False


PORTEUR_TYPE = "organisme-gestionnaire"
PHONE = re.compile(r"0\d{9}|\d{3,4}")
#: A time of day (9h, 13h30, 21 h), not a duration (24 h/24).
HOURS = re.compile(r"\b(?:[01]?\d|2[0-3])\s?[hH]\s?(?:[0-5]\d)?\b")
ACRONYM = re.compile(r"[A-ZÉÈÀ0-9'’-]{3,12}")
#: The offers that need a place to be given.
NEEDS_A_PLACE = {"full_time_hospitalisation", "day_hospitalisation", "screening"}
#: A type that is defined by what it does: its code, and the offers of which it must carry one.
DEFINED_BY_ITS_OFFER = {
    "caarud": ("caarud_without_harm_reduction", {"harm_reduction"}),
    "centre-sante-sexuelle": ("sexual_health_without_screening", {"screening"}),
    "clinique-psychiatrique": ("clinic_without_hospitalisation", {"full_time_hospitalisation", "day_hospitalisation"}),
    "hopital-de-jour": ("day_hospital_without_day_hospitalisation", {"day_hospitalisation"}),
    "programme-etp": ("etp_without_education", {"therapeutic_education"}),
}


def _no_contact(f: EntryFacts) -> bool:
    return not (f.phones or f.emails or f.websites)


def _bad_phone(f: EntryFacts) -> bool:
    return any(not PHONE.fullmatch(phone) for phone in f.phones)


def _acronym_alone(f: EntryFacts) -> bool:
    return (
        f.nature in ("service", "activity")
        and f.label == f.name
        and bool(ACRONYM.fullmatch(f.name))
        and any(c.isalpha() for c in f.name)
    )


def _hours_in_description(f: EntryFacts) -> bool:
    return bool(f.description and HOURS.search(f.description)) and not f.schedules


def _defined_by_its_offer(code: str) -> Callable[[EntryFacts], bool]:
    def broken(f: EntryFacts) -> bool:
        wanted = DEFINED_BY_ITS_OFFER.get(f.type_slug)
        return wanted is not None and wanted[0] == code and not wanted[1] & set(f.offers or [])

    return broken


RULES: tuple[Rule, ...] = (
    # Every listed entry.
    Rule("no_contact", "missing", _no_contact),
    Rule("no_description", "incomplete", lambda f: not (f.description or "").strip()),
    Rule("no_offers", "incomplete", lambda f: not f.offers),
    Rule("no_access", "incomplete", lambda f: f.who_can_contact is None),
    Rule("phone_format", "incomplete", _bad_phone),
    Rule("acronym_without_full_name", "incomplete", _acronym_alone),
    Rule("hours_in_description", "incomplete", _hours_in_description),
    # Placed entries: the address and the pin are what a reader goes by.
    Rule("no_location", "missing", lambda f: not f.immaterial and not f.has_location),
    # Immaterial entries answer from somewhere and for some places (PLAN.md decisions 6 and 7).
    Rule("no_coverage", "missing", lambda f: f.immaterial and f.coverage == 0),
    Rule("no_porteur", "incomplete", lambda f: f.immaterial and not f.has_porteur),
    # By type.
    Rule("line_without_phone", "missing", lambda f: f.type_slug == "ligne-ecoute" and not f.phones),
    Rule(
        "line_access_not_phone",
        "incomplete",
        lambda f: f.type_slug == "ligne-ecoute" and f.access_modes is not None and "phone" not in f.access_modes,
    ),
    Rule(
        "no_on_site_hours",
        "incomplete",
        lambda f: f.type_slug == "permanence-accueil-ecoute" and "on_site" not in f.schedules,
    ),
    Rule(
        "emergency_not_emergency",
        "incomplete",
        lambda f: f.type_slug == "service-urgences" and "emergency" not in (f.care_levels or []),
    ),
    *(
        Rule(code, "incomplete", _defined_by_its_offer(code))
        for code in dict.fromkeys(code for code, _ in DEFINED_BY_ITS_OFFER.values())
    ),
    Rule("porteur_listed", "incomplete", lambda f: f.type_slug == PORTEUR_TYPE and f.listed, unlisted_too=True),
    Rule(
        "porteur_without_siren",
        "incomplete",
        lambda f: f.type_slug == PORTEUR_TYPE and not f.siren,
        unlisted_too=True,
    ),
    # By offer.
    Rule(
        "offer_needs_a_place",
        "missing",
        lambda f: f.immaterial and bool(NEEDS_A_PLACE & set(f.offers or [])),
    ),
    Rule(
        "training_without_website",
        "incomplete",
        lambda f: "training" in (f.offers or []) and not f.websites,
    ),
)


def problems(facts: EntryFacts) -> list[tuple[str, str]]:
    """The (code, severity) of every rule the entry breaks: what is missing first, then what is
    to complete, each in the order of the catalogue. Nothing for an entry that is not active."""
    if not facts.active:
        return []
    judged = [rule for rule in RULES if facts.listed or rule.unlisted_too]
    if not facts.listed and facts.type_slug == PORTEUR_TYPE:
        judged = [rule for rule in judged if rule.unlisted_too]
    found = [(rule.code, rule.severity) for rule in judged if rule.broken(facts)]
    return sorted(found, key=lambda item: SEVERITIES.index(item[1]))


# --- Gathering the facts --------------------------------------------------------------

# One read for every active entry of a directory (of every directory when none is named): the
# entry's own facts, its type's, its facility's, and the edges the rules count. Pattern
# comprehensions rather than COUNT {}: Neo4j 4.4 (and they read the same on 5).
FACTS = """
MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry)
WHERE ($directory IS NULL OR d.name = $directory) AND e.active = true AND ($uid IS NULL OR e.uid = $uid)
MATCH (e)-[:HAS_EFFECTOR]->(x:Effector)
MATCH (e)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
MATCH (e)-[:HAS_FACILITY]->(f:Facility)
RETURN DISTINCT e.uid AS uid, e.slug AS slug, e.active AS active, e.description AS description,
       e.offers AS offers, e.who_can_contact AS who_can_contact, e.care_levels AS care_levels,
       e.access_modes AS access_modes, e.siren AS siren,
       coalesce(x.name_fr, x.name_en) AS name, coalesce(x.label_fr, x.label_en) AS label,
       t.slug_fr AS type_slug, coalesce(t.name_fr, t.name_en) AS type_name,
       coalesce(t.immaterial, false) AS immaterial, t.nature AS nature,
       size([(e)-[:RUN_BY]->(p) | p]) AS porteurs, size([(e)-[:COVERS]->(c) | c]) AS coverage,
       [(e)-[:HAS_SCHEDULE]->(s:Schedule) | s.channel] AS schedules,
       coalesce(f.street, '') <> '' AND f.location IS NOT NULL AS has_location
"""


def _listed_query() -> str:
    from directory.utils import lists_need, owner_listed

    return (
        "MATCH (d:Directory)-[:HAS_ENTRY]->(e:Entry) "
        "WHERE ($directory IS NULL OR d.name = $directory) AND ($uid IS NULL OR e.uid = $uid) "
        f"AND {owner_listed('d', 'e')} AND {lists_need('d', 'e')} RETURN DISTINCT e.uid AS uid"
    )


async def _contacts(uids: list[str]) -> dict[str, dict[str, list[str]]]:
    """The phones, emails and websites of each entry, from the address book."""
    from uuid import UUID

    from addressbook.models import Contact, Email, PhoneNumber, Website

    found: dict[str, dict[str, list[str]]] = {}
    keyed = {}
    for uid in uids:
        try:
            keyed[UUID(uid)] = uid
        except ValueError:
            continue
    by_pk: dict[int, str] = {}
    async for contact in Contact.objects.filter(neomodel_uid__in=list(keyed)):
        by_pk[contact.pk] = keyed[contact.neomodel_uid]
    for model, column, key in ((PhoneNumber, "phone", "phones"), (Email, "email", "emails"), (Website, "url", "websites")):
        async for row in model.objects.filter(contact_id__in=list(by_pk)).values("contact_id", column):
            if row[column]:
                found.setdefault(by_pk[row["contact_id"]], {}).setdefault(key, []).append(row[column])
    return found


async def _gather(directory: str | None, uid: str | None) -> list[EntryFacts]:
    rows = await read(FACTS, directory=directory, uid=uid)
    listed = {row["uid"] for row in await read(_listed_query(), directory=directory, uid=uid)}
    contacts = await _contacts([row["uid"] for row in rows])
    out = []
    for row in rows:
        mine = contacts.get(row["uid"], {})
        out.append(
            EntryFacts(
                uid=row["uid"],
                slug=row["slug"],
                name=row["name"] or "",
                label=row["label"],
                type_slug=row["type_slug"],
                immaterial=bool(row["immaterial"]),
                nature=row["nature"],
                listed=row["uid"] in listed,
                active=bool(row["active"]),
                description=row["description"],
                offers=row["offers"],
                who_can_contact=row["who_can_contact"],
                care_levels=row["care_levels"],
                siren=row["siren"],
                has_porteur=bool(row["porteurs"]),
                coverage=row["coverage"],
                schedules=sorted(row["schedules"]),
                has_location=bool(row["has_location"]),
                phones=sorted(mine.get("phones", [])),
                emails=sorted(mine.get("emails", [])),
                websites=sorted(mine.get("websites", [])),
                access_modes=row["access_modes"],
            )
        )
    return out


async def directory_facts(directory: str) -> list[EntryFacts]:
    """The active entries of a directory, each with what the rules read."""
    return await _gather(directory, None)


async def entry_facts(uid: str, directory: str | None = None) -> EntryFacts | None:
    """One entry, gathered as the directory's are; None when no such active entry is held. With no
    directory named, it is listed when any directory holding it lists it."""
    found = await _gather(directory, uid)
    return found[0] if found else None


async def directory_report(directory: str) -> list[dict]:
    """Every problem of the directory, grouped by rule, what is missing first: for each rule its
    code, severity and the entries that break it (uid, slug, name, label, type), by name."""
    entries = await directory_facts(directory)
    types = {row["uid"]: row["type_name"] for row in await read(FACTS, directory=directory, uid=None)}
    groups: dict[str, dict] = {}
    for facts in entries:
        for code, severity in problems(facts):
            group = groups.setdefault(code, {"code": code, "severity": severity, "entries": []})
            group["entries"].append(
                {"uid": facts.uid, "slug": facts.slug, "name": facts.name, "label": facts.label, "type": types.get(facts.uid)}
            )
    order = {rule.code: position for position, rule in enumerate(RULES)}
    for group in groups.values():
        group["entries"].sort(key=lambda entry: (entry["name"] or "").casefold())
    return sorted(groups.values(), key=lambda group: (SEVERITIES.index(group["severity"]), order[group["code"]]))
