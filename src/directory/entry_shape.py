"""The shape of an Entry: the invariant of the graph model, as code.

An Entry states "this person, in this occupation, at this place, listed in
this directory": exactly one HAS_EFFECTOR, one HAS_EFFECTOR_TYPE and one
HAS_FACILITY, and at least one Directory (HAS_ENTRY). MEMBER_OF is
deliberately absent -- it is legitimately multi-valued.

Nothing in Neo4j enforces this (relationship constraints are rejected by
4.4), and a violation surfaces far from its cause: the entries serializer
emits one row per effector type, so a doubly-typed entry appears twice in
/api/v2/entries. tests/test_entry_graph_model.py checks the whole dataset;
a write that touches an entry's edges checks that one entry here, before and
after, and rolls back rather than leave it malformed.
"""

from neomodel import adb, db

# Relationships an Entry has exactly one of, and what each one means.
SINGLE_VALUED = {
    "HAS_EFFECTOR": "the person the entry describes",
    "HAS_EFFECTOR_TYPE": "the occupation the person is listed under",
    "HAS_FACILITY": "the place the person works at",
}

# Pattern comprehensions rather than COUNT {} subqueries: the graph runs
# Neo4j 4.4, and these read the same on 5.
SHAPE_QUERY = (
    "MATCH (e:Entry {uid: $uid}) RETURN "
    + ", ".join(f"size([(e)-[:{rel}]->(x) | x]) AS {rel}" for rel in SINGLE_VALUED)
    + ", size([(d:Directory)-[:HAS_ENTRY]->(e) | d]) AS directories"
)


def shape_problems(counts: dict[str, int], *, directories: int) -> list[str]:
    """Problem codes for one entry's edge counts, in a stable order:
    "HAS_EFFECTOR_TYPE:2" for a single-valued edge not present exactly once,
    "NO_DIRECTORY" for an entry no directory lists. Empty when well formed."""
    problems = [
        f"{rel}:{counts.get(rel, 0)}" for rel in SINGLE_VALUED if counts.get(rel, 0) != 1
    ]
    if directories < 1:
        problems.append("NO_DIRECTORY")
    return problems


def _problems_from_rows(rows) -> list[str] | None:
    if not rows:
        return None
    *counts, directories = rows[0]
    return shape_problems(dict(zip(SINGLE_VALUED, counts)), directories=directories)


async def entry_shape_problems(uid: str) -> list[str] | None:
    """The entry's problems, or None when no entry has this uid. Inside an
    `async with adb.transaction:` block it reads that transaction's state,
    which is what lets a write check its own result before committing."""
    rows, _ = await adb.cypher_query(SHAPE_QUERY, {"uid": uid})
    return _problems_from_rows(rows)


def sync_entry_shape_problems(uid: str) -> list[str] | None:
    rows, _ = db.cypher_query(SHAPE_QUERY, {"uid": uid})
    return _problems_from_rows(rows)
