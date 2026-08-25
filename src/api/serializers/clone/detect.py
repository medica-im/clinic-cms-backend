"""Does this entry already exist here, and in what form?

Nothing in the app answers that before writing. `assert_slug_is_free` raises 409
*during* the write, which is too late for a preview-and-confirm flow — and the
whole point of cloning between deployments is that a superuser sees what will
happen before it happens.

Two rules, both settled deliberately:

**People resolve silently.** RPPS decides when present, because it is a national
registration number and the same number is the same practitioner. Otherwise name
and gender: a match reuses, no match creates. Neither prompts. The one case that
does not reuse is a source effector whose RPPS differs from a local namesake's —
two RPPS numbers are two registered practitioners, and merging them would be
unrecoverable.

**Facilities can prompt.** Reusing the wrong building rewrites an address or
makes a slug unreachable, and unlike a person a place has no national
identifier, so a superuser confirms anything short of an exact BAN match.
"""
import logging

from neomodel import adb

from api.types.clone import Blocker, CloneMatch, ObjectPlan

logger = logging.getLogger(__name__)

#: Facility fields whose disagreement is worth showing before reuse.
COMPARED = (
    "name", "label", "slug", "building", "street",
    "geographical_complement", "zip", "ban_id", "ban_banId",
)


async def resolve_effector_type(et: dict) -> str | None:
    """The local EffectorType matching the source's, by natural key.

    unique_ID first: it is the stable identifier and is unique_index on both
    stacks. Then slug, then name. Never created — effector types are curated
    reference data, and a clone inventing one would put a new occupation into
    the directory as a side effect of copying a person.
    """
    for field, value in (("unique_ID", et.get("unique_ID")),
                         ("slug_fr", et.get("slug")),
                         ("name_fr", et.get("name"))):
        if not value:
            continue
        rows, _ = await adb.cypher_query(
            f"MATCH (t:EffectorType) WHERE t.{field} = $v RETURN t.uid LIMIT 1",
            {"v": value},
        )
        if rows:
            return rows[0][0]
    return None


async def resolve_commune(address: dict) -> str | None:
    """The local Commune for an incoming address, by name and postcode."""
    city = (address or {}).get("city")
    if not city:
        return None
    rows, _ = await adb.cypher_query(
        """
        MATCH (c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]
              ->(:DepartmentOfFrance)
        WHERE c.name_fr = $city
        RETURN c.uid LIMIT 1
        """,
        {"city": city},
    )
    return rows[0][0] if rows else None


async def plan_effector(full: dict) -> tuple[ObjectPlan, list[str]]:
    """Which local effector this entry's person is, or that they are new."""
    warnings: list[str] = []
    name = (full.get("name") or "").strip()
    gender = full.get("gender")
    rpps = (full.get("rpps") or {}).get("rpps") if isinstance(full.get("rpps"), dict) else None

    if rpps:
        rows, _ = await adb.cypher_query(
            "MATCH (e:HealthWorker) WHERE e.rpps = $rpps RETURN e.uid, e.name_fr LIMIT 1",
            {"rpps": int(rpps)},
        )
        if rows:
            uid, local_name = rows[0]
            return ObjectPlan(
                matches=[CloneMatch(
                    kind="exact", reason="rpps", local_uid=uid,
                    local={"name": local_name, "rpps": rpps},
                    incoming={"name": name, "rpps": rpps},
                )],
                default_resolution="reuse", auto=True, local_uid=uid,
            ), warnings

    rows, _ = await adb.cypher_query(
        """
        MATCH (e:Effector)
        WHERE toLower(e.name_fr) = toLower($name)
          AND coalesce(e.gender,'') = coalesce($gender,'')
        RETURN e.uid, e.name_fr, e.rpps LIMIT 1
        """,
        {"name": name, "gender": gender},
    )
    if not rows:
        return ObjectPlan(default_resolution="create", auto=True), warnings

    uid, local_name, local_rpps = rows[0]
    if rpps and local_rpps and int(local_rpps) != int(rpps):
        # Same name, different registration: two people. Creating is the safe
        # answer, and the superuser is told rather than asked.
        warnings.append(
            f"'{name}' also exists here with a different RPPS "
            f"({local_rpps} vs {rpps}); a new person was created"
        )
        return ObjectPlan(default_resolution="create", auto=True), warnings

    return ObjectPlan(
        matches=[CloneMatch(
            kind="exact", reason="name_gender", local_uid=uid,
            local={"name": local_name}, incoming={"name": name},
        )],
        default_resolution="reuse", auto=True, local_uid=uid,
    ), warnings


async def plan_facility(full: dict, org_uid: str) -> ObjectPlan:
    """Which local facility this entry sits at, and whether to ask.

    Scoped to this organization's own facilities, the same scope
    assert_slug_is_free uses: two unrelated organizations are each entitled to a
    "pharmacie", and only a clash within one is a problem.
    """
    address = full.get("address") or {}
    facility = full.get("facility") or {}
    incoming = {
        "name": facility.get("name"), "label": facility.get("label"),
        "slug": facility.get("slug"), "street": address.get("street"),
        "zip": address.get("zip"), "building": address.get("building"),
        "geographical_complement": address.get("geographical_complement"),
        "ban_id": full.get("ban_id"), "ban_banId": full.get("ban_banId"),
        "city": address.get("city"),
    }

    rows, _ = await adb.cypher_query(
        """
        MATCH (f:Facility)-[:PART_OF]->(o) WHERE o.uid = $org
        OPTIONAL MATCH (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        RETURN f.uid, f.name, f.label, f.slug, f.street, f.zip, f.building,
               f.geographical_complement, f.ban_id, f.ban_banId, c.name_fr
        """,
        {"org": org_uid},
    )
    candidates = [{
        "uid": r[0], "name": r[1], "label": r[2], "slug": r[3], "street": r[4],
        "zip": r[5], "building": r[6], "geographical_complement": r[7],
        "ban_id": r[8], "ban_banId": r[9], "city": r[10],
    } for r in rows]

    def norm(v):
        return (v or "").strip().lower()

    def differing(local):
        return [f for f in COMPARED if norm(local.get(f)) != norm(incoming.get(f))]

    def match_for(local, reason, kind):
        return CloneMatch(
            kind=kind, reason=reason, local_uid=local["uid"],
            local={k: local.get(k) for k in COMPARED},
            incoming={k: incoming.get(k) for k in COMPARED},
            differing_fields=differing(local),
        )

    # Strongest first. BAN identifies a building; the rest are heuristics.
    for local in candidates:
        if incoming["ban_id"] and local["ban_id"] == incoming["ban_id"]:
            m = match_for(local, "ban_id", "exact")
            return ObjectPlan(
                matches=[m], default_resolution="reuse",
                auto=not m.differing_fields, local_uid=local["uid"],
            )

    for local in candidates:
        if (incoming["street"] and norm(local["street"]) == norm(incoming["street"])
                and norm(local["zip"]) == norm(incoming["zip"])
                and norm(local["city"]) == norm(incoming["city"])):
            return ObjectPlan(
                matches=[match_for(local, "address", "warn")],
                default_resolution="reuse", auto=False, local_uid=local["uid"],
            )

    warn_matches = [
        match_for(local, "name", "warn")
        for local in candidates
        if incoming["name"] and norm(local["name"]) == norm(incoming["name"])
    ] + [
        match_for(local, "slug", "warn")
        for local in candidates
        if incoming["slug"] and norm(local["slug"]) == norm(incoming["slug"])
    ]
    if warn_matches:
        return ObjectPlan(
            matches=warn_matches, default_resolution="reuse",
            auto=False, local_uid=warn_matches[0].local_uid,
        )

    return ObjectPlan(default_resolution="create", auto=True)


async def entry_already_here(effector_uid: str | None, effector_type_uid: str | None,
                             facility_uid: str | None) -> str | None:
    """The local entry with this exact (person, occupation, place), if any.

    This is create_entry's own identity rule, checked before writing rather than
    hit as a 452 after an effector and a facility have already been created.
    """
    if not (effector_uid and effector_type_uid and facility_uid):
        return None
    rows, _ = await adb.cypher_query(
        """
        MATCH (entry:Entry {active: true})-[:HAS_EFFECTOR]->(e:Effector {uid: $e})
        MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType {uid: $t})
        MATCH (entry)-[:HAS_FACILITY]->(f:Facility {uid: $f})
        RETURN entry.slug LIMIT 1
        """,
        {"e": effector_uid, "t": effector_type_uid, "f": facility_uid},
    )
    return rows[0][0] if rows else None


async def already_here(entries: list[dict]) -> dict[str, str]:
    """Which of these source entries this instance already has.

    Keyed by source uid, valued with the local entry's slug so the list can
    link to what already exists rather than only greying a row out.

    Matched on the person's name and their occupation, not on uid: uids are
    per-deployment, so the same practitioner is a different node here. That is
    looser than the identity rule create_entry enforces — which is
    (effector, effector_type, facility) — and deliberately so. This runs over a
    whole directory to decorate a list, before any facility has been resolved,
    and its job is to stop a superuser selecting an entry that preflight would
    only reject later. Preflight remains the authority; a row greyed out here
    is a courtesy, not the gate.
    """
    wanted = [
        {"name": (e.get("name") or "").strip().lower(),
         "type": ((e.get("effector_type") or {}).get("name") or "").strip().lower(),
         "uid": e.get("uid")}
        for e in entries
        if e.get("uid") and e.get("name")
    ]
    if not wanted:
        return {}
    rows, _ = await adb.cypher_query(
        """
        UNWIND $wanted AS w
        MATCH (entry:Entry {active: true})-[:HAS_EFFECTOR]->(eff:Effector)
        MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
        WHERE toLower(eff.name_fr) = w.name AND toLower(t.name_fr) = w.type
        RETURN w.uid AS source_uid, entry.slug AS slug
        """,
        {"wanted": wanted},
    )
    return {uid: slug for uid, slug in rows if uid and slug}
