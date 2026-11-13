"""Import a directory's entries from a spec: porteurs first, then the entries.

The spec (built outside the app, e.g. the santé mentale notes' payloads.py) names
everything the way people do, because uids differ on every backend:

    {"directory": "<Directory.name>",
     "porteurs": [{"key", "name", "label", "type", "siren", "facility", "manages"}
                  | {"key", "existing": "<entry slug>"}],
     "entries":  [{"key", "name", "label", "type", "existing", "siren", "facility",
                   "run_by", "manages", "coverage", "facets",
                   "phones", "emails", "websites", "description"}]}

- a type is an EffectorType slug_fr; manages are Condition, Situation or Need slugs;
- a facility is {"name", "address": <BAN fields>, "building"}, or {"porteur": key}
  for a service answering from its porteur's premises (PLAN.md, decision 6);
- run_by is a porteur key or another entry's key;
- coverage is [{"department": code} | {"country": code}];
- "existing" names an entry already in the directory by its slug: it is reused and
  given its porteur, what it manages, its coverage and facets.

preflight() lists every name that does not resolve; import_spec() refuses to write
anything until that list is empty. Every write is found-or-created by a natural key
(facility: street and zip; effector: creator directory and slug; entry: effector,
type and facility), so a rerun after a failure finishes the job and a rerun after
success changes nothing.
"""
from collections import Counter
from dataclasses import dataclass, field

from django.utils.text import slugify

from api.graph import read, write
from directory.coverage import set_coverage
from directory.entry_shape import entry_shape_problems
from directory.facets import ENTRY_FACETS
from directory.manages import set_manages, unknown_slugs
from directory.run_by import set_run_by

PLACES = {"department": "DepartmentOfFrance", "country": "Country"}


@dataclass
class Report:
    created: Counter = field(default_factory=Counter)
    reused: Counter = field(default_factory=Counter)
    uids: dict = field(default_factory=dict)


def selected(spec: dict, only: set[str] | None) -> tuple[list[dict], list[dict]]:
    """The entries named by `only` (all when None), and the porteurs they need."""
    entries = [e for e in spec["entries"] if only is None or e["key"] in only]
    needed = {e["run_by"] for e in entries if e.get("run_by")}
    needed |= {e["facility"]["porteur"] for e in entries if (e.get("facility") or {}).get("porteur")}
    porteurs = [p for p in spec["porteurs"] if only is None or p["key"] in needed]
    return porteurs, entries


async def _one(query: str, **params):
    rows = await read(query, **params)
    return next(iter(rows[0].values())) if len(rows) == 1 else None


async def preflight(spec: dict, only: set[str] | None = None) -> list[str]:
    """Every name in the spec that does not resolve on this backend, in spec order."""
    problems = []
    directory = spec["directory"]
    if not await read("MATCH (d:Directory {name: $d}) RETURN d.uid", d=directory):
        return [f"directory '{directory}' is missing"]
    porteurs, entries = selected(spec, only)
    keys = {p["key"] for p in spec["porteurs"]} | {e["key"] for e in spec["entries"]}
    for item in porteurs + entries:
        key = item["key"]
        if item.get("existing"):
            if await _one("MATCH (:Directory {name: $d})-[:HAS_ENTRY]->(e:Entry {slug: $s}) RETURN e.uid",
                          d=directory, s=item["existing"]) is None:
                problems.append(f"{key}: no entry '{item['existing']}' in directory '{directory}'")
        else:
            if await _one("MATCH (t:EffectorType {slug_fr: $s}) RETURN t.uid", s=item["type"]) is None:
                problems.append(f"{key}: effector type '{item['type']}' is missing")
            facility = item.get("facility")
            if not facility:
                problems.append(f"{key}: no facility")
            elif "address" in facility:
                city = facility["address"]["city"]
                if await _one("MATCH (c:Commune {name_fr: $n}) RETURN c.uid", n=city) is None:
                    problems.append(f"{key}: commune '{city}' is missing")
            elif facility["porteur"] not in keys:
                problems.append(f"{key}: unknown porteur '{facility['porteur']}'")
        for slug in await unknown_slugs(item.get("manages") or []):
            problems.append(f"{key}: unknown manages '{slug}'")
        for place in item.get("coverage") or []:
            (kind, code), = place.items()
            if await _one(f"MATCH (t:{PLACES[kind]} {{code: $c}}) RETURN t.uid", c=code) is None:
                problems.append(f"{key}: unknown {kind} '{code}'")
        if item.get("run_by") and item["run_by"] not in keys:
            problems.append(f"{key}: unknown porteur '{item['run_by']}'")
    return problems


async def _facility(spec_facility: dict, report: Report) -> str:
    address = spec_facility["address"]
    found = await _one("MATCH (f:Facility {street: $street, zip: $zip}) RETURN f.uid LIMIT 1",
                       street=address["street"], zip=address["zip"])
    if found:
        report.reused["facility"] += 1
        return found
    rows = await write(
        """
        MATCH (c:Commune {name_fr: $city})
        CREATE (f:Facility {uid: replace(randomUUID(), '-', ''), name: $name, label: '', street: $street,
                            zip: $zip, building: $building, ban_id: $ban_id, ban_banId: $ban_banId, zoom: 18,
                            location: point({latitude: $lat, longitude: $lon, crs: 'wgs-84'}),
                            createdAt: timestamp(), updatedAt: timestamp()})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        RETURN f.uid AS uid
        """,
        city=address["city"], name=spec_facility["name"], street=address["street"], zip=address["zip"],
        building=spec_facility.get("building"), ban_id=address.get("ban_id"), ban_banId=address.get("ban_banId"),
        lat=address["latitude"], lon=address["longitude"],
    )
    report.created["facility"] += 1
    return rows[0]["uid"]


async def _effector(name: str, label: str | None, creator_directory: str, report: Report) -> str:
    slug = slugify(name)
    found = await _one("MATCH (x:Effector {creator_directory: $d, slug_fr: $s}) RETURN x.uid",
                       d=creator_directory, s=slug)
    if found:
        report.reused["effector"] += 1
        return found
    rows = await write(
        """
        CREATE (x:Effector {uid: replace(randomUUID(), '-', ''), name_fr: $name, label_fr: $label, slug_fr: $slug,
                            creator_directory: $d, createdAt: timestamp(), updatedAt: timestamp()})
        RETURN x.uid AS uid
        """,
        name=name, label=label or name, slug=slug, d=creator_directory,
    )
    report.created["effector"] += 1
    return rows[0]["uid"]


async def _neomodel_connected() -> None:
    """neomodel opens its driver on the first cypher_query, never on a node query."""
    from neomodel import adb

    if adb.driver is None:
        await adb.cypher_query("RETURN 1")


async def _entry(effector: str, type_slug: str, facility: str, directory: str, report: Report) -> str:
    from directory.models.agraph import Effector, EffectorType, Entry, Facility
    from directory.slug import generate_entry_slugs

    await _neomodel_connected()

    found = await _one(
        "MATCH (:Effector {uid: $x})<-[:HAS_EFFECTOR]-(e:Entry)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {slug_fr: $t}), "
        "(e)-[:HAS_FACILITY]->(:Facility {uid: $f}) RETURN e.uid",
        x=effector, t=type_slug, f=facility,
    )
    if found:
        report.reused["entry"] += 1
        uid = found
    else:
        rows = await write(
            """
            MATCH (x:Effector {uid: $x}), (t:EffectorType {slug_fr: $t}), (f:Facility {uid: $f})
            CREATE (e:Entry {uid: replace(randomUUID(), '-', ''), active: true, access: 'anonymous',
                             createdAt: timestamp(), updatedAt: timestamp()})
            CREATE (e)-[:HAS_EFFECTOR]->(x), (e)-[:HAS_EFFECTOR_TYPE]->(t), (e)-[:HAS_FACILITY]->(f)
            RETURN e.uid AS uid
            """,
            x=effector, t=type_slug, f=facility,
        )
        uid = rows[0]["uid"]
        report.created["entry"] += 1
    await write("MATCH (d:Directory {name: $d}), (e:Entry {uid: $e}) MERGE (d)-[:HAS_ENTRY]->(e)", d=directory, e=uid)
    entry = await Entry.nodes.get(uid=uid)
    if not entry.slug:
        slugs = await generate_entry_slugs(
            await Effector.nodes.get(uid=effector), await Facility.nodes.get(uid=facility),
            await EffectorType.nodes.get(slug_fr=type_slug), count=1,
        )
        if not slugs:
            raise ValueError(f"no free slug for entry {uid}")
        entry.slug = slugs[0]
        await entry.save()
    problems = await entry_shape_problems(uid)
    if problems:
        raise ValueError(f"entry {uid} is malformed: {problems}")
    return uid


async def _describe(uid: str, item: dict) -> None:
    """Identity, facets, what it manages and where it answers: replaced each run."""
    facets = {name: (item.get("facets") or {}).get(name) for name in ENTRY_FACETS}
    await write("MATCH (e:Entry {uid: $e}) SET e += $props", e=uid,
                props={**facets, **({"siren": item["siren"]} if item.get("siren") else {})})
    await set_manages(uid, item.get("manages") or [])
    places = []
    for place in item.get("coverage") or []:
        (kind, code), = place.items()
        places.append(await _one(f"MATCH (t:{PLACES[kind]} {{code: $c}}) RETURN t.uid", c=code))
    await set_coverage(uid, places)


async def _contacts(uid: str, item: dict, organization, changed_by) -> None:
    from access.models import Role
    from addressbook.models import Contact, Email, PhoneNumber, Profile, Website

    roles = [r async for r in Role.objects.all()]
    contact, _ = await Contact.objects.aget_or_create(neomodel_uid=uid)
    items = [(PhoneNumber, {"phone": p}, {"type": PhoneNumber.TelephoneType.WORK}) for p in item.get("phones") or []]
    items += [(Email, {"email": e}, {}) for e in item.get("emails") or []]
    items += [(Website, {"url": w}, {}) for w in item.get("websites") or []]
    for model, lookup, extra in items:
        made, created = await model.objects.aget_or_create(
            contact=contact, **lookup, defaults={**extra, "public_visible": True, "contact_visible": True})
        if created:
            await made.roles.aset(roles)
            if organization is not None:
                await made.organization.aset([organization])
    if item.get("description") and organization is not None and changed_by is not None:
        profile, created = await Profile.objects.aget_or_create(
            contact=contact,
            defaults={"text": item["description"], "organization": organization, "changed_by": changed_by})
        if created:
            await profile.roles.aset(roles)


async def _organization(directory: str):
    from directory.models import Directory
    from facility.models import Organization

    row = await Directory.objects.filter(name=directory).select_related("site").afirst()
    return await Organization.objects.filter(site=row.site).afirst() if row else None


async def import_spec(spec: dict, creator_directory: str, only: set[str] | None = None,
                      contacts: bool = True, changed_by=None) -> Report:
    """Write the spec's porteurs and entries (those in `only`, with their porteurs)."""
    problems = await preflight(spec, only)
    if problems:
        raise ValueError("; ".join(problems))
    directory = spec["directory"]
    porteurs, entries = selected(spec, only)
    organization = await _organization(directory) if contacts else None
    report = Report()
    facilities = {}
    for item in porteurs + entries:
        key = item["key"]
        if item.get("existing"):
            uid = await _one("MATCH (:Directory {name: $d})-[:HAS_ENTRY]->(e:Entry {slug: $s}) RETURN e.uid",
                             d=directory, s=item["existing"])
            report.reused["entry"] += 1
        else:
            facility = item["facility"]
            if "porteur" in facility:
                facility_uid = facilities.get(facility["porteur"]) or await _one(
                    "MATCH (:Entry {uid: $e})-[:HAS_FACILITY]->(f) RETURN f.uid", e=report.uids[facility["porteur"]])
            else:
                facility_uid = await _facility(facility, report)
            effector = await _effector(item["name"], item.get("label"), creator_directory, report)
            uid = await _entry(effector, item["type"], facility_uid, directory, report)
            facilities[key] = facility_uid
            if contacts:
                await _contacts(uid, item, organization, changed_by)
        report.uids[key] = uid
        await _describe(uid, item)
    for item in entries:
        if item.get("run_by"):
            await set_run_by(report.uids[item["key"]], report.uids[item["run_by"]])
    return report
