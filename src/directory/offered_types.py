"""The categories (effector types) a directory offers its entries.

    (Directory)-[:OFFERS_EFFECTOR_TYPE]->(EffectorType)

No edge means no limit. A superuser may use any type; anyone else creating an
entry, or changing its type, is held to the set. Edges rather than a list of
uids: MERGE keeps it a set, and a deleted type takes its edge with it.

See tests/api/test_directory_offered_effector_types.py.
"""
from neomodel import adb

SUPERUSER = "superuser"

OFFERED = """
MATCH (:Directory {name: $name})-[:OFFERS_EFFECTOR_TYPE]->(t:EffectorType)
RETURN t.uid
"""

OFFER = """
MATCH (d:Directory {name: $name}), (t:EffectorType {uid: $type})
MERGE (d)-[:OFFERS_EFFECTOR_TYPE]->(t)
RETURN t.uid
"""

WITHDRAW = """
MATCH (:Directory {name: $name})-[r:OFFERS_EFFECTOR_TYPE]->(:EffectorType {uid: $type})
DELETE r
"""

WITHDRAW_ALL = """
MATCH (:Directory {name: $name})-[r:OFFERS_EFFECTOR_TYPE]->()
DELETE r
"""


class TypeNotOffered(Exception):
    """The directory offers a set of types and this one is not in it."""


async def offered_type_uids(directory_name: str) -> set[str] | None:
    """The uids of the types the directory offers; None when it offers all."""
    rows, _ = await adb.cypher_query(OFFERED, {"name": directory_name})
    return {row[0] for row in rows} or None


async def offer(directory_name: str, type_uid: str) -> bool:
    """Add a type to the set; False when the directory or the type is unknown."""
    rows, _ = await adb.cypher_query(OFFER, {"name": directory_name, "type": type_uid})
    return bool(rows)


async def withdraw(directory_name: str, type_uid: str) -> None:
    await adb.cypher_query(WITHDRAW, {"name": directory_name, "type": type_uid})


async def withdraw_all(directory_name: str) -> None:
    """Back to every type — the default."""
    await adb.cypher_query(WITHDRAW_ALL, {"name": directory_name})


async def site_directory_name(site) -> str | None:
    """The site's directory, the one whose set holds; None when it has no
    single one (then nothing is limited)."""
    from directory.models import Directory
    from directory.utils import async_get_directory_for_site
    try:
        return (await async_get_directory_for_site(site)).name
    except (Directory.DoesNotExist, Directory.MultipleObjectsReturned):
        return None


async def check_type_offered(directory_name: str, type_uid: str, role: str | None) -> None:
    """Raise TypeNotOffered unless the caller may give an entry this type here."""
    if role == SUPERUSER:
        return
    offered = await offered_type_uids(directory_name)
    if offered is not None and type_uid not in offered:
        raise TypeNotOffered(type_uid)
