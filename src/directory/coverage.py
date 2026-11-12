"""COVERS: (entry:Entry)-[:COVERS]->(Commune | DepartmentOfFrance | RegionOfFrance | Country).

Where a service without premises answers: the 3114 covers the country, ÉcoGéPsy a
region. Zero or more per entry; "national" is the Country. It is what an immaterial
entry shows in place of an address. Written through the official driver and checked
before anything is changed: a refusal leaves the entry's edges exactly as they were.
"""
from api.graph import read, write

PLACE = "(t:Country OR t:RegionOfFrance OR t:DepartmentOfFrance OR t:Commune)"
#: Widest first, the order a page reads them in.
KINDS = ("country", "region", "department", "commune")


class CoverageRefused(Exception):
    """`code` is unknown_entry or unknown_place; `uids` names the unknown places."""

    def __init__(self, code: str, uids: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.uids = uids or []


async def unknown_places(uids: list[str]) -> list[str]:
    """The uids that name no commune, department, region or country, in the order given."""
    found = await read(f"MATCH (t) WHERE {PLACE} AND t.uid IN $uids RETURN DISTINCT t.uid AS uid", uids=uids)
    known = {row["uid"] for row in found}
    return [uid for uid in dict.fromkeys(uids) if uid not in known]


async def set_coverage(entry_uid: str, uids: list[str]) -> None:
    """Make `uids` exactly where the entry answers, replacing the rest."""
    if not await read("MATCH (e:Entry {uid: $uid}) RETURN e.uid AS uid", uid=entry_uid):
        raise CoverageRefused("unknown_entry")
    wanted = list(dict.fromkeys(uids))
    unknown = await unknown_places(wanted)
    if unknown:
        raise CoverageRefused("unknown_place", unknown)
    await write(
        f"""
        MATCH (e:Entry {{uid: $entry}})
        OPTIONAL MATCH (e)-[old:COVERS]->()
        DELETE old
        WITH DISTINCT e
        UNWIND $uids AS uid
        MATCH (t) WHERE {PLACE} AND t.uid = uid
        MERGE (e)-[:COVERS]->(t)
        """,
        entry=entry_uid,
        uids=wanted,
    )


async def get_coverage(entry_uid: str) -> list[dict]:
    rows = await read(
        f"""
        MATCH (:Entry {{uid: $uid}})-[:COVERS]->(t) WHERE {PLACE}
        RETURN t.uid AS uid, coalesce(t.name_fr, t.name) AS name,
               CASE WHEN t:Country THEN 'country' WHEN t:RegionOfFrance THEN 'region'
                    WHEN t:DepartmentOfFrance THEN 'department' ELSE 'commune' END AS kind
        """,
        uid=entry_uid,
    )
    return sorted(rows, key=lambda row: (KINDS.index(row["kind"]), row["name"] or ""))
