"""One active Access per user and site, enforced by Neo4j.

The active Access carries activeKey = "<user uid>:<entry uid>"; superseding it
removes the key. A uniqueness constraint ignores nodes without the property, so
it binds the current role and leaves the history alone. The constraint is
declared on the model (Access.activeKey, unique_index=True), so neomodel's
install_labels creates it on any database, new or restored.

Writers MERGE the active Access on its key rather than CREATE it: on a uniquely
constrained property, Neo4j makes concurrent MERGEs agree on one node.
"""
from neomodel import db


def active_key(user_uid: str, entry_uid: str) -> str:
    return f"{user_uid}:{entry_uid}"


# A suspended Access is still active: a suspended member is still a member.
MEMBER_BY_EMAIL = """
MATCH (u:User)-[:HAS_ACCESS]->(:Access {active: true})
      -[:ACCESS_TO]->(:Entry {uid: $entry_uid})
WHERE toLower(u.email) = toLower($email)
RETURN u.uid LIMIT 1
"""


async def is_member(email: str, entry_uid: str) -> bool:
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        MEMBER_BY_EMAIL, {"email": email, "entry_uid": entry_uid}
    )
    return bool(rows)


def is_member_sync(email: str, entry_uid: str) -> bool:
    rows, _ = db.cypher_query(
        MEMBER_BY_EMAIL, {"email": email, "entry_uid": entry_uid}
    )
    return bool(rows)


def install_constraint() -> None:
    # Imported here: a migration loads this module on machines with no Neo4j.
    from access.neomodels import Access

    db.install_labels(Access)


# A suspension found on any duplicate is carried to the one kept: merging
# duplicates must never lift a suspension.
_KEEP_SUSPENSION = """
FOREACH (s IN CASE WHEN keep.suspendedAt IS NULL THEN suspended[0..1] ELSE [] END |
    SET keep.suspendedAt = s.suspendedAt,
        keep.suspensionReason = s.suspensionReason)
"""

# The same role twice is an artefact of simultaneous sign-ins, never a decision,
# so the extras are deleted: kept as history they would read as a role change
# that never happened. The oldest, the original grant, stays.
DELETE_IDENTICAL_DUPLICATES = """
MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry)
WITH u, e, ac ORDER BY ac.createdAt
WITH u, e, collect(ac) AS acs
WHERE size(acs) > 1 AND all(a IN acs WHERE a.role = acs[0].role)
WITH acs[0] AS keep, acs[1..] AS extras,
     [a IN acs WHERE a.suspendedAt IS NOT NULL] AS suspended
""" + _KEEP_SUSPENSION + """
WITH extras
UNWIND extras AS extra
DETACH DELETE extra
RETURN count(*)
"""

# Different roles are real history: the most recent grant is the current role,
# and the older ones end when it began.
RETIRE_SUPERSEDED_DUPLICATES = """
MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry)
WITH u, e, ac ORDER BY ac.createdAt DESC
WITH u, e, collect(ac) AS acs
WHERE size(acs) > 1
WITH acs[0] AS keep, acs[1..] AS older,
     [a IN acs WHERE a.suspendedAt IS NOT NULL] AS suspended
""" + _KEEP_SUSPENSION + """
WITH keep, older
UNWIND older AS old
SET old.active = false, old.supersededAt = keep.createdAt
REMOVE old.activeKey
RETURN count(*)
"""

SET_ACTIVE_KEYS = """
MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry)
SET ac.activeKey = u.uid + ':' + e.uid
RETURN count(ac)
"""

# Nobody is invited to a site they already belong to.
DELETE_MEMBER_INVITATIONS = """
MATCH (i:Invitee)-[:INVITED_TO]->(e:Entry)
WHERE i.redeemedAt IS NULL
  AND EXISTS {
    MATCH (u:User)-[:HAS_ACCESS]->(:Access {active: true})-[:ACCESS_TO]->(e)
    WHERE toLower(u.email) = toLower(i.email)
  }
DETACH DELETE i
RETURN count(*)
"""


def enforce_single_active_access() -> dict[str, int]:
    """Bring the graph to one active Access per user and site, then lock it in.

    Idempotent: on a graph that already holds the invariant every count is
    zero except `keyed`, and the constraint already exists.
    """
    counts = {}
    for name, query in (
        ("deleted", DELETE_IDENTICAL_DUPLICATES),
        ("retired", RETIRE_SUPERSEDED_DUPLICATES),
        ("keyed", SET_ACTIVE_KEYS),
        ("invitations_deleted", DELETE_MEMBER_INVITATIONS),
    ):
        rows, _ = db.cypher_query(query)
        counts[name] = rows[0][0] if rows else 0
    install_constraint()
    return counts
