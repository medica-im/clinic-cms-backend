"""What decides a directory's lists, read on the source and applied on the target.

See tests/api/test_clone_directory_settings.py.
"""
from neomodel import adb

from api.types.clone import DirectorySnapshot, SettingDifference

#: Applied unless unticked: they decide what the directory shows.
DEFAULT_APPLIED = frozenset({"lists_needs", "offered_types"})
KEYS = ("lists_needs", "offered_types", "list_owner_entry", "minimum_role")

READ = """
MATCH (d:Directory {name: $name})
OPTIONAL MATCH (d)-[:LISTS_NEED]->(n:Need)
WITH d, collect(DISTINCT n.slug) AS needs
OPTIONAL MATCH (d)-[:OFFERS_EFFECTOR_TYPE]->(t:EffectorType)
RETURN needs, collect(DISTINCT t.name_fr), coalesce(d.list_owner_entry, true), coalesce(d.minimum_role, 'anonymous')
"""

#: (relationship, label, key property) of each set.
SETS = {
    "lists_needs": ("LISTS_NEED", "Need", "slug"),
    "offered_types": ("OFFERS_EFFECTOR_TYPE", "EffectorType", "name_fr"),
}


async def read(name: str) -> DirectorySnapshot | None:
    rows, _ = await adb.cypher_query(READ, {"name": name}, resolve_objects=False)
    if not rows:
        return None
    needs, types, listed, role = rows[0]
    return DirectorySnapshot(lists_needs=sorted(needs), offered_types=sorted(types),
                             list_owner_entry=listed, minimum_role=role)


async def unknown_here(source: DirectorySnapshot) -> dict[str, list[str]]:
    """The needs and types the source names that do not exist on this server."""
    out = {}
    for key, (_, label, prop) in SETS.items():
        wanted = getattr(source, key)
        rows, _ = await adb.cypher_query(
            f"MATCH (x:{label}) WHERE x.{prop} IN $keys RETURN x.{prop}", {"keys": wanted},
            resolve_objects=False)
        missing = sorted(set(wanted) - {r[0] for r in rows})
        if missing:
            out[key] = missing
    return out


def differences(source: DirectorySnapshot, here: DirectorySnapshot,
                unknown: dict[str, list[str]]) -> list[SettingDifference]:
    return [
        SettingDifference(key=key, source=getattr(source, key), here=getattr(here, key),
                          missing_here=unknown.get(key, []), applied_by_default=key in DEFAULT_APPLIED)
        for key in KEYS
        if getattr(source, key) != getattr(here, key)
    ]


async def _make_set(name: str, key: str, wanted: list[str]) -> list[str]:
    rel, label, prop = SETS[key]
    await adb.cypher_query(
        f"MATCH (:Directory {{name: $name}})-[r:{rel}]->(x:{label}) WHERE NOT x.{prop} IN $keys DELETE r",
        {"name": name, "keys": wanted})
    rows, _ = await adb.cypher_query(
        f"MATCH (d:Directory {{name: $name}}) MATCH (x:{label}) WHERE x.{prop} IN $keys "
        f"MERGE (d)-[:{rel}]->(x) RETURN x.{prop}",
        {"name": name, "keys": wanted}, resolve_objects=False)
    missing = sorted(set(wanted) - {r[0] for r in rows})
    return [f"{key}: '{m}' does not exist here, skipped" for m in missing]


async def apply(name: str, source: DirectorySnapshot, keys: list[str], *, main: bool) -> list[str]:
    """Make the chosen settings of this directory the source's; the warnings."""
    warnings: list[str] = []
    for key in SETS:
        if key in keys:
            warnings += await _make_set(name, key, getattr(source, key))
    if "list_owner_entry" in keys:
        await adb.cypher_query("MATCH (d:Directory {name: $name}) SET d.list_owner_entry = $v",
                               {"name": name, "v": source.list_owner_entry})
    if "minimum_role" in keys:
        if main and source.minimum_role != "anonymous":
            warnings.append("minimum_role: a site's own directory is always public, kept")
        else:
            await adb.cypher_query("MATCH (d:Directory {name: $name}) SET d.minimum_role = $v",
                                   {"name": name, "v": source.minimum_role})
    return warnings
