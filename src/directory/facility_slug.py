"""Slugs for facilities: readable, and held by no other facility anywhere."""
import re
import secrets
from dataclasses import dataclass

from django.utils.text import slugify
from neomodel import adb


HOUSE_NUMBER = re.compile(r"^\s*\d+\s*(bis|ter|quater)?\s*,?\s*", re.I)


def street_name(street: str | None) -> str:
    """The street without its house number: '10 Rue Paul Bert' -> 'Rue Paul Bert'.

    The number says nothing to a reader and makes the URL read as a house
    rather than a place, so it only comes back when the name alone is not
    enough (two cabinets on one street).
    """
    return HOUSE_NUMBER.sub("", street or "").strip()


def facility_slug_candidates(
    name: str | None,
    commune: str | None = None,
    street: str | None = None,
    zip: str | None = None,
) -> list[str]:
    """The slugs a facility could have, most readable first: the name, then
    the commune, the street (without, then with its number) and the postcode
    added in turn."""
    base = slugify(name or "")
    if base:
        named = street_name(street)
        variants = [
            [],
            [commune],
            [named, commune],
            [street, commune],
            [commune, zip],
            [street, commune, zip],
        ]
    else:
        # A plain address has no name: it is named by its street, number included,
        # which is all that tells two of them on one street apart.
        base = slugify(street or "")
        if not base:
            return []
        variants = [[], [commune], [commune, zip]]
    candidates: list[str] = []
    for parts in variants:
        if any(not p for p in parts):
            continue
        slug = "-".join([base, *(slugify(p) for p in parts)])
        if slug not in candidates:
            candidates.append(slug)
    return candidates


async def taken_facility_slugs(slugs: list[str], exclude_uid: str | None = None) -> set[str]:
    """Which of these slugs another facility holds."""
    if not slugs:
        return set()
    rows, _ = await adb.cypher_query(
        "MATCH (f:Facility) WHERE f.slug IN $slugs AND ($exclude IS NULL OR f.uid <> $exclude) "
        "RETURN DISTINCT f.slug",
        {"slugs": slugs, "exclude": exclude_uid},
    )
    return {row[0] for row in rows}


async def generate_facility_slugs(
    name: str | None,
    commune: str | None = None,
    street: str | None = None,
    zip: str | None = None,
    *,
    count: int = 1,
    exclude_uid: str | None = None,
) -> list[str]:
    """Up to `count` free slugs, most readable first. When every readable one is
    taken, the most specific gets a short random suffix. `exclude_uid` is the
    facility being edited, which may keep its own slug."""
    candidates = facility_slug_candidates(name, commune, street, zip)
    if not candidates:
        return []
    taken = await taken_facility_slugs(candidates, exclude_uid)
    free = [s for s in candidates if s not in taken]
    stem = "-".join(filter(None, [slugify(name or ""), slugify(commune or "")]))
    while len(free) < count:
        suffixed = f"{stem}-{secrets.token_hex(2)}"
        if suffixed not in free and not await taken_facility_slugs([suffixed], exclude_uid):
            free.append(suffixed)
    return free[:count]


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


async def check_facility_slug(
    name: str,
    commune: str | None = None,
    street: str | None = None,
    zip: str | None = None,
    *,
    slug: str | None = None,
    exclude_uid: str | None = None,
) -> dict:
    """Without `slug`, the most readable free slug and two alternatives. With
    one, whether it is free ("invalid" or "taken" if not) and, if not, three
    free ones to pick instead."""
    place = (name, commune, street, zip)
    if slug is None:
        free = await generate_facility_slugs(*place, count=3, exclude_uid=exclude_uid)
        return {"slug": free[0] if free else None, "free": bool(free),
                "reason": None if free else "invalid", "suggestions": free[1:]}
    if not SLUG.match(slug):
        reason = "invalid"
    elif await taken_facility_slugs([slug], exclude_uid):
        reason = "taken"
    else:
        reason = None
    suggestions = [] if reason is None else await generate_facility_slugs(*place, count=3, exclude_uid=exclude_uid)
    return {"slug": slug, "free": reason is None, "reason": reason, "suggestions": suggestions}


async def slug_for_new_facility(
    slug: str | None,
    name: str | None,
    commune_uid: str | None,
    street: str | None,
    zip: str | None,
) -> str | None:
    """The slug to store for a facility being created: the one the person
    chose, else the most readable free one."""
    if slug and slug.strip():
        return slug.strip()
    commune = None
    if commune_uid:
        rows, _ = await adb.cypher_query(
            "MATCH (c:Commune {uid: $uid}) RETURN c.name_fr", {"uid": commune_uid}
        )
        commune = rows[0][0] if rows else None
    generated = await generate_facility_slugs(name, commune, street, zip, count=1)
    return generated[0] if generated else None


@dataclass
class SlugRepair:
    uid: str
    name: str | None
    old: str | None
    new: str
    reason: str  # "shared" | "missing"


FACILITIES = """
MATCH (f:Facility)
OPTIONAL MATCH (f)<-[:HAS_FACILITY]-(e:Entry {active: true})
OPTIONAL MATCH (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
RETURN f.uid, f.name, f.slug, f.street, f.zip, head(collect(DISTINCT c.name_fr)), count(DISTINCT e)
"""


IDENTITIES = """
MATCH (f:Facility)<-[:HAS_FACILITY]-(e:Entry {active: true})
OPTIONAL MATCH (e)-[:HAS_EFFECTOR]->(p:Effector)
OPTIONAL MATCH (e)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
RETURN f.uid, p.uid, t.uid
"""


async def _facilities() -> list[dict]:
    rows, _ = await adb.cypher_query(FACILITIES)
    return [
        {"uid": r[0], "name": r[1], "slug": r[2], "street": r[3], "zip": r[4], "commune": r[5], "entries": r[6]}
        for r in rows
    ]


def _has_attachments_sync(uid: str) -> bool:
    import uuid

    from addressbook.models import Contact
    from facility.models import PlaceImage

    try:
        key = uuid.UUID(uid)
    except ValueError:
        return False
    if PlaceImage.objects.filter(neomodel_uid=key).exists():
        return True
    contact = Contact.objects.filter(neomodel_uid=key).first()
    if contact is None:
        return False
    return any(getattr(contact, rel).exists() for rel in ("phonenumbers", "emails", "websites", "socialnetworks"))


async def _has_attachments(uid: str) -> bool:
    """Whether Postgres holds contacts or images for this facility."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(_has_attachments_sync)(uid)


@dataclass
class FacilityMerge:
    keep_uid: str
    drop_uid: str
    name: str | None
    entries: int
    #: Why a person must look at it instead; None when it can be merged as planned.
    blocked: str | None


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


async def plan_facility_merges(has_attachments=None) -> list[FacilityMerge]:
    """Facilities with one slug, one name and one address are one place recorded
    several times. The one with the most active entries (then the smallest uid)
    is kept. A duplicate with contacts or images, or whose entries would collide
    with the kept one's (same person, same occupation), is only reported."""
    has_attachments = has_attachments or _has_attachments
    facilities = await _facilities()
    rows, _ = await adb.cypher_query(IDENTITIES)
    identities: dict[str, set] = {}
    for uid, person, occupation in rows:
        identities.setdefault(uid, set()).add((person, occupation))

    groups: dict[tuple, list[dict]] = {}
    for f in facilities:
        if f["slug"]:
            key = (f["slug"], _norm(f["name"]), _norm(f["street"]), _norm(f["zip"]))
            groups.setdefault(key, []).append(f)

    merges: list[FacilityMerge] = []
    for holders in groups.values():
        if len(holders) < 2:
            continue
        holders.sort(key=lambda f: (-f["entries"], f["uid"]))
        keep, *drops = holders
        for drop in drops:
            blocked = None
            if await has_attachments(drop["uid"]):
                blocked = "has contacts or images"
            elif identities.get(drop["uid"], set()) & identities.get(keep["uid"], set()):
                blocked = "same person and occupation already at the kept facility"
            merges.append(FacilityMerge(keep["uid"], drop["uid"], drop["name"], drop["entries"], blocked))
    return merges


MOVE_ENTRIES = """
MATCH (e:Entry)-[r:HAS_FACILITY]->(d:Facility {uid: $drop})
MATCH (k:Facility {uid: $keep})
MERGE (e)-[:HAS_FACILITY]->(k)
DELETE r
"""

MOVE_PEOPLE = """
MATCH (d:Facility {uid: $drop})-[:%s]->(u:User)
MATCH (k:Facility {uid: $keep})
MERGE (k)-[:%s]->(u)
"""

COLLISIONS = """
MATCH (d:Facility {uid: $drop})<-[:HAS_FACILITY]-(de:Entry {active: true})
MATCH (k:Facility {uid: $keep})<-[:HAS_FACILITY]-(ke:Entry {active: true})
MATCH (de)-[:HAS_EFFECTOR]->(p)<-[:HAS_EFFECTOR]-(ke)
MATCH (de)-[:HAS_EFFECTOR_TYPE]->(t)<-[:HAS_EFFECTOR_TYPE]-(ke)
RETURN count(*)
"""


async def merge_facility(keep_uid: str, drop_uid: str) -> None:
    """Point the duplicate's entries and owners at the kept facility, then delete
    the duplicate, which must be unused by then. Refuses, changing nothing, when
    a person would then hold the same occupation twice at the kept facility."""
    if keep_uid == drop_uid:
        raise ValueError("a facility cannot be merged into itself")
    rows, _ = await adb.cypher_query(COLLISIONS, {"keep": keep_uid, "drop": drop_uid})
    if rows and rows[0][0]:
        raise ValueError("same person and occupation already at the kept facility")
    params = {"keep": keep_uid, "drop": drop_uid}
    await adb.cypher_query(MOVE_ENTRIES, params)
    for edge in ("OWNED_BY", "CREATED_BY"):
        await adb.cypher_query(MOVE_PEOPLE % (edge, edge), params)
    await adb.cypher_query(
        "MATCH (d:Facility {uid: $drop}) WHERE NOT (d)<-[:HAS_FACILITY]-() DETACH DELETE d", params
    )


async def plan_slug_repairs(has_attachments=None) -> list[SlugRepair]:
    """What it would take for every facility to hold a slug of its own: a
    slug shared by several different places stays with the one it describes (a
    slug the generator could produce from that facility's own name and address),
    then the one with the most active entries, then the smallest uid; the others
    get a generated one, and so does any named facility with no slug. A
    facility with neither name nor slug is a plain address, reached by uid, and
    is left alone. Duplicates of one place are merged, not renamed
    (plan_facility_merges). Reads the graph, writes nothing."""
    duplicates = {m.drop_uid for m in await plan_facility_merges(has_attachments)}
    facilities = [f for f in await _facilities() if f["uid"] not in duplicates]
    by_slug: dict[str, list[dict]] = {}
    for f in facilities:
        if f["slug"]:
            by_slug.setdefault(f["slug"], []).append(f)

    def describes(f: dict) -> bool:
        return f["slug"] in facility_slug_candidates(f["name"], f["commune"], f["street"], f["zip"])

    todo: list[tuple[dict, str]] = []
    for holders in by_slug.values():
        if len(holders) > 1:
            holders.sort(key=lambda f: (not describes(f), -f["entries"], f["uid"]))
            todo += [(f, "shared") for f in holders[1:]]
    todo += [(f, "missing") for f in facilities if not f["slug"] and (f["name"] or "").strip()]
    todo.sort(key=lambda t: t[0]["uid"])

    kept = {f["slug"] for f in facilities if f["slug"]}
    reserved: set[str] = set()
    repairs: list[SlugRepair] = []
    for f, reason in todo:
        free = await generate_facility_slugs(
            f["name"], f["commune"], f["street"], f["zip"], count=len(reserved) + 1, exclude_uid=f["uid"]
        )
        new = next((s for s in free if s not in reserved and s not in kept), None)
        if new is None:
            continue
        reserved.add(new)
        repairs.append(SlugRepair(f["uid"], f["name"], f["slug"], new, reason))
    return repairs
