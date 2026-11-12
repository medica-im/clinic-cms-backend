"""MANAGES from an Entry: (entry:Entry)-[:MANAGES]->(Condition | Situation | Need).

What this one entry handles, as opposed to the type-level MANAGES of its
EffectorType, which stays and is never touched here. Targets are matched by slug
(the same node has a different uid on each Neo4j server). Written through the
official driver and checked before anything is changed: a refusal leaves the
entry's edges exactly as they were.
"""
from api.graph import read, write

TARGET = "(t:Condition OR t:Situation OR t:Need)"


class ManagesRefused(Exception):
    """`code` is unknown_entry or unknown_target; `slugs` names the unknown ones."""

    def __init__(self, code: str, slugs: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.slugs = slugs or []


async def unknown_slugs(slugs: list[str]) -> list[str]:
    """The slugs that name no Condition, Situation or Need, in the order given."""
    found = await read(
        f"MATCH (t) WHERE {TARGET} AND t.slug IN $slugs RETURN DISTINCT t.slug AS slug", slugs=slugs
    )
    known = {row["slug"] for row in found}
    return [slug for slug in dict.fromkeys(slugs) if slug not in known]


async def set_manages(entry_uid: str, slugs: list[str]) -> None:
    """Make `slugs` exactly what the entry manages, replacing the rest."""
    if not await read("MATCH (e:Entry {uid: $uid}) RETURN e.uid AS uid", uid=entry_uid):
        raise ManagesRefused("unknown_entry")
    wanted = list(dict.fromkeys(slugs))
    unknown = await unknown_slugs(wanted)
    if unknown:
        raise ManagesRefused("unknown_target", unknown)
    await write(
        f"""
        MATCH (e:Entry {{uid: $entry}})
        OPTIONAL MATCH (e)-[old:MANAGES]->(o) WHERE o:Condition OR o:Situation OR o:Need
        DELETE old
        WITH DISTINCT e
        UNWIND $slugs AS slug
        MATCH (t) WHERE {TARGET} AND t.slug = slug
        MERGE (e)-[:MANAGES]->(t)
        """,
        entry=entry_uid,
        slugs=wanted,
    )


async def get_manages(entry_uid: str) -> list[str]:
    rows = await read(
        f"MATCH (:Entry {{uid: $uid}})-[:MANAGES]->(t) WHERE {TARGET} AND t.slug IS NOT NULL "
        "RETURN t.slug AS slug ORDER BY slug",
        uid=entry_uid,
    )
    return [row["slug"] for row in rows]
