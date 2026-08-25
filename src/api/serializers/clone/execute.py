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

from neomodel import adb

from api.serializers.clone import detect
from api.types.clone import CloneResult

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
                    source_org_entry: str | None, creator_uid: str | None) -> CloneResult:
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
