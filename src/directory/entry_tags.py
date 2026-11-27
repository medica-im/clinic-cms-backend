"""TAGS onto an Entry: (tag:Tag)-[:TAGS]->(entry:Entry), set when the entry is created.

A tag means something only for the occupations its category belongs to:
(EffectorType)-[:HAS_TAG_CATEGORY]->(TagCategory)<-[:IS_A]-(Tag). Checked before
anything is written.
"""
from api.graph import read, write


async def unknown_tags(uids: list[str]) -> list[str]:
    """The uids that name no Tag, in the order given."""
    wanted = list(dict.fromkeys(uids))
    found = await read("MATCH (t:Tag) WHERE t.uid IN $uids RETURN t.uid AS uid", uids=wanted)
    known = {row["uid"] for row in found}
    return [uid for uid in wanted if uid not in known]


async def tags_not_for_type(uids: list[str], effector_type: str) -> list[str]:
    """The tags whose category is not one of the effector type's, in the order given."""
    wanted = list(dict.fromkeys(uids))
    found = await read(
        """
        MATCH (:EffectorType {uid: $type})-[:HAS_TAG_CATEGORY]->(:TagCategory)<-[:IS_A]-(t:Tag)
        WHERE t.uid IN $uids
        RETURN DISTINCT t.uid AS uid
        """,
        type=effector_type,
        uids=wanted,
    )
    allowed = {row["uid"] for row in found}
    return [uid for uid in wanted if uid not in allowed]


async def add_tags(entry_uid: str, uids: list[str]) -> None:
    await write(
        """
        MATCH (e:Entry {uid: $entry})
        UNWIND $uids AS uid
        MATCH (t:Tag {uid: uid})
        MERGE (t)-[:TAGS]->(e)
        """,
        entry=entry_uid,
        uids=list(dict.fromkeys(uids)),
    )
