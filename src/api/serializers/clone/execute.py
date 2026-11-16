"""Write one cloned entry, or leave the graph as it was found.

Neo4j gives no cross-statement rollback through neomodel here, so the order is
chosen instead: everything cheap and reversible happens first, and each node
this call creates is recorded so a later failure can undo it.

After the Entry exists the clone stops rolling back. That is the staged-commit
boundary and it is deliberate — the entry is the thing the superuser asked for,
while contacts, images and tags are enrichment they can retry. An entry with no
phone is recoverable by hand; a half-written graph is not.
"""
import logging
import uuid

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.db import IntegrityError
from neomodel import adb
from pydantic import ValidationError

from access.models import Role
from addressbook.models import Contact, Email, PhoneNumber, SocialNetwork, Website
from api.serializers.clone import detect
from api.types.clone import CloneResult
from api.types.entry import EntryFacets
from api.types.schedule import SchedulePut, node_properties
from directory.coverage import set_coverage
from directory.facets import ENTRY_FACETS
from directory.manages import set_manages, unknown_slugs
from directory.run_by import set_run_by

logger = logging.getLogger(__name__)

NEW_UID = "replace(randomUUID(), '-', '')"


class Compensation:
    """The nodes this clone created, so a failure can take them back.

    Only ever deletes what it created, and only when nothing else has come to
    depend on it: a facility another entry has since joined is no longer this
    call's to remove. Whatever it declines to delete is reported rather than
    forced, so the superuser sees an orphan named instead of a silent one.
    """

    def __init__(self):
        self.created: list[tuple[str, str]] = []

    def note(self, label: str, uid: str):
        self.created.append((label, uid))

    async def undo(self) -> list[str]:
        warnings: list[str] = []
        for label, uid in reversed(self.created):
            guard = {"Facility": "HAS_FACILITY", "Effector": "HAS_EFFECTOR"}.get(label)
            if guard:
                rows, _ = await adb.cypher_query(
                    f"MATCH (n:{label} {{uid: $uid}}) "
                    f"OPTIONAL MATCH (e:Entry)-[:{guard}]->(n) "
                    f"RETURN count(e)",
                    {"uid": uid},
                )
                if rows and rows[0][0]:
                    warnings.append(f"orphan_created: {label} {uid} is now in use and was kept")
                    continue
            await adb.cypher_query(
                f"MATCH (n:{label} {{uid: $uid}}) DETACH DELETE n", {"uid": uid}
            )
        return warnings


async def _create_facility(full: dict, commune_uid: str, org_uid: str,
                           slug: str | None, comp: Compensation) -> str:
    address = full.get("address") or {}
    facility = full.get("facility") or {}
    rows, _ = await adb.cypher_query(
        """
        CREATE (f:Facility)
        SET f.uid = """ + NEW_UID + """,
            f.name = $name, f.label = $label, f.slug = $slug,
            f.street = $street, f.zip = $zip, f.building = $building,
            f.geographical_complement = $complement,
            f.ban_id = $ban_id, f.ban_banId = $ban_banId,
            f.zoom = $zoom
        """ + ("""
        SET f.location = point({longitude: $lng, latitude: $lat, crs:'wgs-84'})
        """ if address.get("longitude") and address.get("latitude") else "") + """
        WITH f
        MATCH (c:Commune {uid: $commune})
        // Exactly one commune edge: Facility.commune is cardinality One, and
        // tests/test_facility_graph_model.py enforces it. A second one makes
        // the entries query emit every entry here twice.
        MERGE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        WITH f
        MATCH (o {uid: $org})
        MERGE (f)-[:PART_OF]->(o)
        RETURN f.uid
        """,
        {
            "name": facility.get("name"), "label": facility.get("label"),
            "slug": slug, "street": address.get("street"), "zip": address.get("zip"),
            "building": address.get("building"),
            "complement": address.get("geographical_complement"),
            "ban_id": full.get("ban_id"), "ban_banId": full.get("ban_banId"),
            "zoom": address.get("zoom") or 18,
            "lng": float(address["longitude"]) if address.get("longitude") else None,
            "lat": float(address["latitude"]) if address.get("latitude") else None,
            "commune": commune_uid, "org": org_uid,
        },
    )
    uid = rows[0][0]
    comp.note("Facility", uid)
    return uid


async def _create_effector(full: dict, directory_name: str, comp: Compensation) -> str:
    """The person, with their RPPS written in the same statement as the label.

    One statement on purpose: RPPS is globally unique on :HealthWorker, so a
    duplicate has to fail *here*, while the compensation can still take the
    facility back — not after the entry exists and rollback has stopped.
    """
    rpps = full.get("rpps") if isinstance(full.get("rpps"), dict) else None
    is_hcw = bool(rpps and rpps.get("rpps"))
    rows, _ = await adb.cypher_query(
        "CREATE (e:Effector) "
        "SET e.uid = " + NEW_UID + ", e.name_fr = $name, e.label_fr = $label, "
        "    e.slug_fr = $slug, e.gender = $gender, e.creator_directory = $dir "
        + ("SET e:HealthWorker, e.rpps = $rpps, e.spoken_languages = $langs " if is_hcw else "")
        + "RETURN e.uid",
        {
            "name": full.get("name"), "label": full.get("label") or full.get("name"),
            "slug": full.get("slug"), "gender": full.get("gender"),
            "dir": directory_name,
            "rpps": int(rpps["rpps"]) if is_hcw else None,
            "langs": [l.get("tag") for l in (full.get("spoken_languages") or [])],
        },
    )
    uid = rows[0][0]
    comp.note("Effector", uid)
    return uid


async def clone_one(full: dict, resolution, *, directory_name: str, org_uid: str,
                    source_org_entry: str | None, creator_uid: str | None,
                    organization=None, porteurs: dict[str, str] | None = None,
                    avatar: tuple[str, bytes] | None = None) -> CloneResult:
    """Clone one entry, in the order that keeps a failure recoverable."""
    comp = Compensation()
    warnings: list[str] = []
    source_uid = full.get("uid") or ""

    try:
        # 1. Reference data, read-only. A blocker here costs nothing.
        et_uid = await detect.resolve_effector_type(full.get("effector_type") or {})
        if not et_uid:
            return CloneResult(source_uid=source_uid, status="failed",
                               error="effector type not available on this instance")

        # 2. Facility.
        if resolution.facility == "reuse" and resolution.facility_local_uid:
            facility_uid = resolution.facility_local_uid
        else:
            commune_uid = await detect.resolve_commune(full.get("address") or {})
            if not commune_uid:
                return CloneResult(source_uid=source_uid, status="failed",
                                   error="commune not available on this instance")
            slug = resolution.facility_slug_override or (full.get("facility") or {}).get("slug")
            facility_uid = await _create_facility(full, commune_uid, org_uid, slug, comp)

        # 3. Effector. RPPS uniqueness fails here, while step 2 is still undoable.
        if resolution.effector == "reuse" and resolution.effector_local_uid:
            effector_uid = resolution.effector_local_uid
        else:
            effector_uid = await _create_effector(full, directory_name, comp)

        # 4. The identity rule create_entry enforces with a 452, checked before
        #    the entry exists rather than after.
        existing = await detect.entry_already_here(effector_uid, et_uid, facility_uid)
        if existing:
            warnings += await comp.undo()
            return CloneResult(source_uid=source_uid, status="failed",
                               error=f"an entry for this person, occupation and place "
                                     f"already exists here: {existing}",
                               warnings=warnings)

        # 5. The entry itself. Past here nothing rolls back.
        rows, _ = await adb.cypher_query(
            """
            CREATE (entry:Entry)
            SET entry.uid = """ + NEW_UID + """,
                entry.active = true, entry.access = $access,
                entry.carte_vitale = $carte_vitale, entry.payment = $payment,
                entry.third_party_payer = $tpp, entry.convention = $convention
            WITH entry
            MATCH (e:Effector {uid: $effector}) MERGE (entry)-[:HAS_EFFECTOR]->(e)
            WITH entry
            MATCH (t:EffectorType {uid: $etype}) MERGE (entry)-[:HAS_EFFECTOR_TYPE]->(t)
            WITH entry
            MATCH (f:Facility {uid: $facility}) MERGE (entry)-[:HAS_FACILITY]->(f)
            WITH entry
            MATCH (d:Directory {name: $dir}) MERGE (d)-[:HAS_ENTRY]->(entry)
            RETURN entry.uid
            """,
            {
                "access": full.get("access") or "anonymous",
                "carte_vitale": full.get("carte_vitale"),
                "payment": [p.get("name") for p in (full.get("payment_methods") or [])],
                "tpp": [t.get("name") for t in (full.get("third_party_payers") or [])],
                "convention": (full.get("convention") or {}).get("name"),
                "effector": effector_uid, "etype": et_uid,
                "facility": facility_uid, "dir": directory_name,
            },
        )
        entry_uid = rows[0][0]
        comp.note("Entry", entry_uid)

        # An entry lives in two stores. Postgres holds a Contact row keyed by
        # the entry's uid, and that row is what emails, phones, websites and
        # social media links hang off — each of those endpoints fetches it with
        # `aget(neomodel_uid=...)` and 404s without it.
        #
        # Writing the Entry with raw Cypher skips the ordinary creation path in
        # serializers/entries.py, which is where that row is normally made, so
        # it has to be made here too. Cloned entries that lacked one were
        # complete and visible in every graph respect while refusing every
        # attempt to give them contact details.
        #
        # get_or_create, not create: a uid collision is not a reason to fail a
        # clone that has already passed the point of no rollback.
        try:
            await Contact.objects.aget_or_create(neomodel_uid=entry_uid)
        except IntegrityError:
            pass

        if creator_uid:
            await adb.cypher_query(
                "MATCH (entry:Entry {uid:$e}), (u:User {uid:$u}) "
                "MERGE (entry)-[:CREATED_BY]->(u)",
                {"e": entry_uid, "u": creator_uid},
            )

        # A fresh slug, never the source's: Entry.slug is globally unique.
        slug = await _assign_slug(entry_uid, full)

        # 7b. Memberships — Entry edges only. The neo4j Organization node is
        # retired, so an edge to one is left out rather than recreated here.
        warnings += await _clone_memberships(
            entry_uid, full, source_org_entry=source_org_entry, org_uid=org_uid
        )

        # 8. What the entry says and manages, where it answers, who runs it, how to
        #    reach it, its hours, picture and tags: each failure a warning.
        warnings += await _enrich(entry_uid, full, porteurs=porteurs or {},
                                  organization=organization, avatar=avatar)

        return CloneResult(
            source_uid=source_uid, status="created", entry_uid=entry_uid,
            entry_slug=slug, effector_uid=effector_uid, facility_uid=facility_uid,
            warnings=warnings,
        )
    except Exception as exc:
        logger.exception("clone failed for %s", source_uid)
        warnings += await comp.undo()
        return CloneResult(source_uid=source_uid, status="failed",
                           error=str(exc), warnings=warnings)


async def _assign_slug(entry_uid: str, full: dict) -> str | None:
    from directory.models.agraph import (
        Entry as AsyncEntry, Effector as AsyncEffector,
        EffectorType as AsyncEffectorType, Facility as AsyncFacility,
    )
    from directory.slug import generate_entry_slugs

    entry = await AsyncEntry.nodes.get(uid=entry_uid)
    effector = (await entry.effector.all())[0]
    effector_type = (await entry.effector_type.all())[0]
    facility = (await entry.facility.all())[0]
    slugs = await generate_entry_slugs(effector, facility, effector_type, count=1)
    if not slugs:
        # A failed clone result, not a 500: the entry exists and is fixable.
        raise RuntimeError("could not generate a unique slug for the cloned entry")
    entry.slug = slugs[0]
    await entry.save()
    return slugs[0]


async def _clone_memberships(entry_uid: str, full: dict, *,
                             source_org_entry: str | None, org_uid: str) -> list[str]:
    """MEMBER_OF edges, remapping the source organization to this one.

    `full['organizations']` — edges to the retired neo4j Organization node — is
    deliberately ignored. Only `memberships`, which point at entries, travel.
    """
    warnings: list[str] = []
    for uid in (full.get("memberships") or []):
        if source_org_entry and uid == source_org_entry:
            # The edge means "belongs to the publishing organization", and that
            # referent differs per instance.
            await adb.cypher_query(
                "MATCH (a:Entry {uid:$a}), (b:Entry {uid:$b}) MERGE (a)-[:MEMBER_OF]->(b)",
                {"a": entry_uid, "b": org_uid},
            )
            continue
        rows, _ = await adb.cypher_query(
            "MATCH (b:Entry {uid:$b}) RETURN b.uid", {"b": uid}
        )
        if rows:
            await adb.cypher_query(
                "MATCH (a:Entry {uid:$a}), (b:Entry {uid:$b}) MERGE (a)-[:MEMBER_OF]->(b)",
                {"a": entry_uid, "b": uid},
            )
        else:
            # Never create a membership target: a dangling edge, or an invented
            # organization, is worse than a missing link the superuser can add.
            warnings.append(f"membership {uid} does not exist here and was not created")
    return warnings


# --- Enrichment: past the point of no rollback ------------------------------------------
#
# Reference data is matched, never created, as effector types are: what an entry manages
# by slug, a tag by name, a place by its kind and code. What is not here is named in a
# warning, so the superuser knows what to sync (the console) before cloning again.


async def _enrich(entry_uid: str, full: dict, *, porteurs: dict[str, str], organization,
                  avatar: tuple[str, bytes] | None) -> list[str]:
    steps = (
        ("facets", lambda: _say(entry_uid, full)),
        ("manages", lambda: _manage(entry_uid, full)),
        ("coverage", lambda: _cover(entry_uid, full)),
        ("run_by", lambda: _run_by(entry_uid, full, porteurs)),
        ("contacts", lambda: _reach(entry_uid, full, organization)),
        ("schedules", lambda: _hours(entry_uid, full)),
        ("avatar", lambda: _picture(entry_uid, full, avatar)),
        ("tags", lambda: _tag(entry_uid, full)),
    )
    warnings: list[str] = []
    for name, step in steps:
        try:
            warnings += await step()
        except Exception as exc:
            logger.exception("clone of %s: %s failed", entry_uid, name)
            warnings.append(f"{name}: {exc}")
    return warnings


async def _say(entry_uid: str, full: dict) -> list[str]:
    """The description, the SIREN and every facet this instance's vocabulary accepts."""
    props, warnings = {}, []
    for name in ("description", "siren"):
        if full.get(name):
            props[name] = full[name]
    for facet in ENTRY_FACETS:
        if full.get(facet) is None:
            continue
        try:
            props[facet] = getattr(EntryFacets.model_validate({facet: full[facet]}), facet)
        except ValidationError:
            warnings.append(f"facets: {facet} left out, unknown here: {full[facet]!r}")
    if props:
        await adb.cypher_query("MATCH (e:Entry {uid: $e}) SET e += $props", {"e": entry_uid, "props": props})
    return warnings


async def _manage(entry_uid: str, full: dict) -> list[str]:
    slugs = list(dict.fromkeys(full.get("manages") or []))
    if not slugs:
        return []
    unknown = await unknown_slugs(slugs)
    known = [slug for slug in slugs if slug not in unknown]
    if known:
        await set_manages(entry_uid, known)
    return [f"manages: not on this instance: {', '.join(unknown)}"] if unknown else []


PLACE_BY_CODE = {"country": "Country", "region": "RegionOfFrance", "department": "DepartmentOfFrance"}


async def _local_place(place: dict) -> str | None:
    """The same place here: by its code, or a commune by its name and its département's code."""
    kind = place.get("kind")
    if kind in PLACE_BY_CODE and place.get("code"):
        rows, _ = await adb.cypher_query(
            f"MATCH (t:{PLACE_BY_CODE[kind]} {{code: $code}}) RETURN t.uid LIMIT 1", {"code": place["code"]})
    elif kind == "commune" and place.get("name") and place.get("department"):
        rows, _ = await adb.cypher_query(
            "MATCH (c:Commune {name_fr: $name})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->"
            "(:DepartmentOfFrance {code: $department}) RETURN c.uid LIMIT 1",
            {"name": place["name"], "department": place["department"]})
    else:
        rows = []
    return rows[0][0] if rows else None


async def _cover(entry_uid: str, full: dict) -> list[str]:
    found, missing = [], []
    for place in full.get("coverage") or []:
        uid = await _local_place(place)
        if uid:
            found.append(uid)
        else:
            missing.append(place.get("name") or place.get("code") or "?")
    if found:
        await set_coverage(entry_uid, found)
    return [f"coverage: not on this instance: {', '.join(missing)}"] if missing else []


async def _run_by(entry_uid: str, full: dict, porteurs: dict[str, str]) -> list[str]:
    """The porteur the batch cloned, or one already here under the same slug."""
    source = full.get("run_by")
    if not source:
        return []
    local = porteurs.get(source.get("uid"))
    if not local and source.get("slug"):
        rows, _ = await adb.cypher_query("MATCH (p:Entry {slug: $s}) RETURN p.uid LIMIT 1", {"s": source["slug"]})
        local = rows[0][0] if rows else None
    if not local:
        name = source.get("name") or source.get("slug") or source.get("uid")
        return [f"run_by: porteur not on this instance, clone it first: {name}"]
    await set_run_by(entry_uid, local)
    return []


#: Each kind of contact detail: the source's list key, the model, what identifies an item
#: on its contact, and what else it carries.
CONTACT_KINDS = (
    ("phones", PhoneNumber, lambda i: ({"phone": i["phone"]}, {"type": i.get("type") or PhoneNumber.TelephoneType.WORK})),
    ("emails", Email, lambda i: ({"email": i["email"]}, {})),
    ("websites", Website, lambda i: ({"url": i["url"]}, {})),
    ("socialnetworks", SocialNetwork, lambda i: ({"type": i["type"], "url": i.get("url") or ""},
                                                {"handle": i.get("handle") or ""})),
)


@sync_to_async
def _reach_sync(entry_uid: str, full: dict, organization) -> list[str]:
    """Each detail with the roles that may see it on the source; public when anonymous may."""
    contact, _ = Contact.objects.get_or_create(neomodel_uid=entry_uid)
    roles = {role.name: role for role in Role.objects.all()}
    for key, model, identify in CONTACT_KINDS:
        for item in full.get(key) or []:
            lookup, extra = identify(item)
            names = item.get("roles") or []
            obj, created = model.objects.get_or_create(
                contact=contact, **lookup,
                defaults={**extra, "public_visible": "anonymous" in names, "contact_visible": True})
            if created:
                obj.roles.set([roles[name] for name in names if name in roles])
                if organization is not None:
                    obj.organization.set([organization])
    return []


async def _reach(entry_uid: str, full: dict, organization) -> list[str]:
    return await _reach_sync(entry_uid, full, organization)


async def _hours(entry_uid: str, full: dict) -> list[str]:
    warnings = []
    for item in full.get("schedules") or []:
        try:
            schedule = SchedulePut(
                entry=entry_uid, channel=item["channel"], label=item.get("label"),
                holidays=item.get("holidays") or "closed",
                days={int(day): periods for day, periods in (item.get("days") or {}).items()},
            )
        except (ValidationError, KeyError, ValueError) as exc:
            warnings.append(f"schedules: one left out: {exc}")
            continue
        await adb.cypher_query(
            "MATCH (e:Entry {uid: $e}) CREATE (e)-[:HAS_SCHEDULE]->(s:Schedule {uid: $uid}) SET s += $props",
            {"e": entry_uid, "uid": uuid.uuid4().hex, "props": node_properties(schedule)})
    return warnings


async def _picture(entry_uid: str, full: dict, avatar: tuple[str, bytes] | None) -> list[str]:
    """The picture file, downloaded from the source by the router, and who may see it."""
    source = full.get("avatar")
    if not source:
        return []
    if not avatar:
        return ["avatar: the picture could not be downloaded from the source"]
    filename, content = avatar

    @sync_to_async
    def save():
        contact, _ = Contact.objects.get_or_create(neomodel_uid=entry_uid)
        contact.profile_image.save(filename, ContentFile(content), save=False)
        contact.avatar_access = source.get("access") or "anonymous"
        contact.save()

    await save()
    return []


async def _tag(entry_uid: str, full: dict) -> list[str]:
    names = [tag.get("name") for tag in full.get("tags") or [] if tag.get("name")]
    if not names:
        return []
    rows, _ = await adb.cypher_query(
        "MATCH (t:Tag) WHERE t.name IN $names MATCH (e:Entry {uid: $e}) MERGE (t)-[:TAGS]->(e) RETURN t.name",
        {"names": names, "e": entry_uid})
    found = {row[0] for row in rows}
    missing = [name for name in names if name not in found]
    return [f"tags: not on this instance: {', '.join(missing)}"] if missing else []


async def porteurs_to_add(fulls: list[dict], fetch, *, batch: set[str]) -> list[dict]:
    """The porteurs these entries are run by that are neither in the batch nor here, read
    from the source with `fetch(uid)`, and their own porteurs: an unlisted porteur is never
    in the source's entry list, so nobody could pick it."""
    added: list[dict] = []
    seen = set(batch)
    queue = list(fulls)
    while queue:
        source = queue.pop(0).get("run_by") or {}
        uid = source.get("uid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if source.get("slug"):
            rows, _ = await adb.cypher_query("MATCH (p:Entry {slug: $s}) RETURN p.uid LIMIT 1", {"s": source["slug"]})
            if rows:
                continue
        porteur = await fetch(uid)
        if porteur:
            added.append(porteur)
            queue.append(porteur)
    return added


async def missing_here(full: dict, *, batch: set[str]) -> list[str]:
    """What cloning `full` here would leave out, by the same matching the clone uses: for
    preflight, before anything is written. A porteur in the batch is not missing."""
    missing: list[str] = []
    unknown = await unknown_slugs(list(dict.fromkeys(full.get("manages") or [])))
    if unknown:
        missing.append(f"manages: not on this instance: {', '.join(unknown)}")
    places = [p.get("name") or p.get("code") or "?" for p in full.get("coverage") or [] if not await _local_place(p)]
    if places:
        missing.append(f"coverage: not on this instance: {', '.join(places)}")
    source = full.get("run_by")
    if source and source.get("uid") not in batch:
        rows, _ = await adb.cypher_query("MATCH (p:Entry {slug: $s}) RETURN p.uid LIMIT 1", {"s": source.get("slug")})
        if not rows:
            name = source.get("name") or source.get("slug") or source.get("uid")
            missing.append(f"run_by: porteur not on this instance, clone it first: {name}")
    names = [tag.get("name") for tag in full.get("tags") or [] if tag.get("name")]
    if names:
        rows, _ = await adb.cypher_query("MATCH (t:Tag) WHERE t.name IN $n RETURN t.name", {"n": names})
        absent = [name for name in names if name not in {row[0] for row in rows}]
        if absent:
            missing.append(f"tags: not on this instance: {', '.join(absent)}")
    return missing


# --- A batch -------------------------------------------------------------------------------


def porteurs_first(batch: list[dict]) -> list[dict]:
    """The batch with each porteur before the services it runs, otherwise in its order."""
    by_uid = {full.get("uid"): full for full in batch}
    ordered, seen = [], set()

    def visit(full: dict, path: tuple = ()):
        uid = full.get("uid")
        if uid in seen or uid in path:
            return
        porteur = (full.get("run_by") or {}).get("uid")
        if porteur in by_uid:
            visit(by_uid[porteur], path + (uid,))
        seen.add(uid)
        ordered.append(full)

    for full in batch:
        visit(full)
    return ordered


async def clone_batch(items: list[tuple[dict, "Resolution"]], *,
                      avatars: dict[str, tuple[str, bytes]] | None = None, **context) -> list[CloneResult]:
    """Clone a batch: a porteur before the services it runs, so each finds its porteur's
    local uid, and a service without premises reuses the facility its porteur just got.
    Results come back in the order asked."""
    resolution_of = {full.get("uid"): res for full, res in items}
    porteurs: dict[str, str] = {}
    facilities: dict[str, str] = {}
    results: dict[str, CloneResult] = {}
    for full in porteurs_first([full for full, _ in items]):
        res = resolution_of[full.get("uid")]
        source_facility = (full.get("facility") or {}).get("uid")
        if res.facility == "create" and source_facility in facilities:
            res = res.model_copy(update={"facility": "reuse", "facility_local_uid": facilities[source_facility]})
        result = await clone_one(full, res, porteurs=porteurs, avatar=(avatars or {}).get(full.get("uid")), **context)
        if result.status == "created":
            porteurs[full.get("uid")] = result.entry_uid
            if source_facility:
                facilities[source_facility] = result.facility_uid
        results[full.get("uid")] = result
    return [results[full.get("uid")] for full, _ in items]
