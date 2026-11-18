"""RUN_BY: (service:Entry)-[:RUN_BY]->(porteur:Entry).

The porteur is the entry of the organization that runs this one: an
establishment is run by the legal unit that owns it, a service by the hospital
behind it. At most one per entry (see entry_shape.AT_MOST_ONE), chains allowed,
never a loop. Written through the official driver and checked before anything
is changed: a refusal leaves the entry exactly as it was, never half-detached.

MEMBER_OF is a different relationship (a person in an organization's team) and
is not used for this.
"""
import unicodedata

from api.graph import read, write
from directory.siret_rule import run_by_disagrees


class RunByRefused(Exception):
    """`code` is unknown_entry, unknown_porteur, cycle or siret_mismatch."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def _exists(uid: str) -> bool:
    return bool(await read("MATCH (e:Entry {uid: $uid}) RETURN e.uid AS uid", uid=uid))


async def set_run_by(entry_uid: str, porteur_uid: str | None) -> None:
    """Make `porteur_uid` the entry's porteur, replacing any other; None detaches it."""
    if not await _exists(entry_uid):
        raise RunByRefused("unknown_entry")
    if porteur_uid is not None:
        if not await _exists(porteur_uid):
            raise RunByRefused("unknown_porteur")
        # The porteur may not be this entry, nor anything this entry already runs,
        # directly or through a chain: a path from the porteur down to the entry.
        loop = await read(
            "MATCH (p:Entry {uid: $porteur})-[:RUN_BY*0..]->(e:Entry {uid: $entry}) RETURN count(p) AS n",
            porteur=porteur_uid,
            entry=entry_uid,
        )
        if loop[0]["n"]:
            raise RunByRefused("cycle")
        if await run_by_disagrees(entry_uid, porteur_uid):
            raise RunByRefused("siret_mismatch")
    await write(
        """
        MATCH (e:Entry {uid: $entry})
        OPTIONAL MATCH (e)-[old:RUN_BY]->(:Entry)
        DELETE old
        WITH DISTINCT e
        OPTIONAL MATCH (p:Entry {uid: $porteur})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (e)-[:RUN_BY]->(p))
        """,
        entry=entry_uid,
        porteur=porteur_uid,
    )


async def services_of(porteur_uid: str) -> list[str]:
    """The uids of the entries this one runs directly (not through a chain)."""
    rows = await read(
        "MATCH (s:Entry)-[:RUN_BY]->(:Entry {uid: $porteur}) RETURN s.uid AS uid ORDER BY uid",
        porteur=porteur_uid,
    )
    return [row["uid"] for row in rows]


# What an entry's page needs to link to the entries around it. Only the active
# ones: an entry switched off is not shown on another's page. The name is read in
# the site's language, English when it has none.
_RELATED = """
MATCH (e:Entry {uid: $uid})
CALL {
  WITH e
  MATCH (e)-[:RUN_BY]->(p:Entry {active: true})
  RETURN collect(p) AS porteurs, [] AS services
  UNION
  WITH e
  MATCH (s:Entry {active: true})-[:RUN_BY]->(e)
  RETURN [] AS porteurs, collect(s) AS services
}
WITH porteurs, services
UNWIND (porteurs + services) AS n
OPTIONAL MATCH (n)-[:HAS_EFFECTOR]->(f:Effector)
OPTIONAL MATCH (n)-[:HAS_EFFECTOR_TYPE]->(t:EffectorType)
RETURN n.uid AS uid,
       n.slug AS slug,
       coalesce(f[$name], f.name_en) AS name,
       coalesce(f[$label], f.label_en) AS label,
       coalesce(t[$label], t.label_en) AS effector_type,
       coalesce(n.access, 'anonymous') AS access,
       n.siren AS siren,
       n IN porteurs AS is_porteur
"""


def name_order(name: str | None) -> str:
    """Alphabetical as a French reader expects: case and accents do not move a word
    ("Établissement" sits with the E's, not after the Z's)."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


async def related_entries(entry_uid: str, language: str) -> dict:
    """{"run_by": the porteur or None, "services": the entries it runs, by name}."""
    rows = await read(_RELATED, uid=entry_uid, name=f"name_{language}", label=f"label_{language}")
    keys = ("uid", "slug", "name", "label", "effector_type", "access", "siren")
    around = [{key: row[key] for key in keys} for row in rows]
    porteur = next((item for item, row in zip(around, rows) if row["is_porteur"]), None)
    services = sorted(
        (item for item, row in zip(around, rows) if not row["is_porteur"]),
        key=lambda item: name_order(item["name"]),
    )
    return {"run_by": porteur, "services": services}


def visible_around(around: dict, allowed: set[str] | None) -> dict:
    """The entries around one, minus those whose access level the viewer may not see.
    `allowed` is the set api.utils.ALLOWED_ACCESS gives the viewer's role; None (the
    superuser) is not restricted."""
    if allowed is None:
        return around
    porteur = around["run_by"]
    return {
        "run_by": porteur if porteur and porteur["access"] in allowed else None,
        "services": [s for s in around["services"] if s["access"] in allowed],
    }
