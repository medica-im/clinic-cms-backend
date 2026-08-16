"""Reading and writing a user's Access, as single Cypher statements.

A role is superseded, never overwritten. Changing one deactivates the current
Access and creates another, so the previous role survives with the time it
ended and who ended it — the record the history section reads back, and an
audit trail nobody can see is one nobody can check.

Each write here is one statement on purpose. "Deactivate the old, create the
new" done as two round trips has a window in which the user holds no active
Access at all, or two; a request arriving inside it sees a user who is
momentarily nobody. Neo4j runs a single statement in one transaction, which
closes the window without a lock.

The invariant that at most one Access per user per site is active cannot be
expressed as a Neo4j 4.4 constraint — the same reason the Entry graph model is
pinned by test rather than by the database — so it is the writes here that have
to keep it, and tests/api/test_role_change.py that checks they do.
"""
import logging
from time import time_ns
from uuid import uuid4

from neomodel import adb

logger = logging.getLogger(__name__)


def _now() -> int:
    """Milliseconds since the epoch, matching the neomodels' createdAt."""
    return time_ns() // 1_000_000


async def get_access(user_uid: str, entry_uid: str) -> dict | None:
    """The user's active Access for this site, or None.

    Returns the role along with the suspension fields, because every caller
    that wants to know the role also has to know whether it is usable — asking
    those as two questions invites code that checks one and forgets the other.
    """
    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access {active: true})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    RETURN ac.uid AS uid, ac.role AS role, ac.suspendedAt AS suspendedAt,
           ac.suspensionReason AS suspensionReason
    """
    results, meta = await adb.cypher_query(
        query, {"user_uid": user_uid, "entry_uid": entry_uid}
    )
    if not results:
        return None
    return dict(zip(meta, results[0]))


async def count_superusers(entry_uid: str) -> int:
    """How many usable superusers this site has.

    A suspended superuser is not counted: they cannot act, so they are no
    protection against the last usable one stepping down and leaving nobody
    able to promote anyone.
    """
    query = """
    MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true, role: 'superuser'})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    WHERE ac.suspendedAt IS NULL
    RETURN count(DISTINCT u) AS n
    """
    results, _ = await adb.cypher_query(query, {"entry_uid": entry_uid})
    return results[0][0] if results else 0


async def supersede_access(
    user_uid: str,
    entry_uid: str,
    granted: str,
    actor_uid: str | None,
    actor_role: str,
) -> dict:
    """Replace the user's active Access with one carrying the granted role.

    The old node is marked inactive and stamped with when it ended and who
    ended it; the new one records the actor's role *at the time*, rather than
    leaving the history to resolve it on read. An actor demoted next month
    still acted as an administrator today, and a history that looked the role
    up at display time would quietly rewrite itself.

    The actor may be absent — a change made by something other than a signed-in
    user — so SUPERSEDED_BY is only created when there is somebody to point at,
    rather than failing the write or inventing a node.
    """
    now = _now()
    query = """
    MATCH (u:User {uid: $user_uid})
    MATCH (e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (u)-[:HAS_ACCESS]->(old:Access {active: true})-[:ACCESS_TO]->(e)
    SET old.active = false,
        old.supersededAt = $now

    WITH u, e, old
    OPTIONAL MATCH (actor:User {uid: $actor_uid})
    FOREACH (_ IN CASE WHEN old IS NOT NULL AND actor IS NOT NULL THEN [1] ELSE [] END |
        CREATE (old)-[:SUPERSEDED_BY]->(actor)
    )

    WITH u, e, actor
    CREATE (ac:Access {
        uid: $access_uid,
        role: $granted,
        active: true,
        createdAt: $now,
        createdByRole: $actor_role
    })
    CREATE (u)-[:HAS_ACCESS]->(ac)
    CREATE (ac)-[:ACCESS_TO]->(e)
    FOREACH (_ IN CASE WHEN actor IS NOT NULL THEN [1] ELSE [] END |
        CREATE (ac)-[:CREATED_BY]->(actor)
    )
    RETURN ac.uid AS uid, ac.role AS role
    """
    params = {
        "user_uid": user_uid,
        "entry_uid": entry_uid,
        "granted": granted,
        "actor_uid": actor_uid,
        "actor_role": actor_role,
        "access_uid": uuid4().hex,
        "now": now,
    }
    results, meta = await adb.cypher_query(query, params)
    if not results:
        raise LookupError(
            f"no User {user_uid} or Entry {entry_uid} to change the role of"
        )
    logger.info(
        f"Access superseded for User {user_uid}: role={granted} "
        f"by {actor_uid} acting as {actor_role}"
    )
    return dict(zip(meta, results[0]))


async def suspend_access(
    user_uid: str, entry_uid: str, actor_uid: str | None, reason: str | None
) -> bool:
    """Suspend the user's active Access, leaving it active.

    Deliberately not a flip of `active`: a suspended account and a superseded
    one would then be indistinguishable, restoring would mean guessing which
    inactive node to revive, and the identity would vanish along with the
    privileges — leaving the dashboard nothing to explain. The role survives so
    a suspended administrator stays a suspended administrator.
    """
    now = _now()
    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access {active: true})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    SET ac.suspendedAt = $now,
        ac.suspensionReason = $reason

    WITH ac
    OPTIONAL MATCH (actor:User {uid: $actor_uid})
    FOREACH (_ IN CASE WHEN actor IS NOT NULL THEN [1] ELSE [] END |
        CREATE (ac)-[:SUSPENDED_BY]->(actor)
    )
    RETURN ac.uid AS uid
    """
    params = {
        "user_uid": user_uid,
        "entry_uid": entry_uid,
        "actor_uid": actor_uid,
        "reason": reason,
        "now": now,
    }
    results, _ = await adb.cypher_query(query, params)
    return bool(results)


async def restore_access(user_uid: str, entry_uid: str) -> bool:
    """Lift a suspension, returning the access to ordinary use.

    The SUSPENDED_BY relationship goes too. Left in place it would say the
    account is suspended by someone while the timestamp says it is not, and the
    next reader would have to guess which half to believe. What was done stays
    in the superseded history, which is where the audit trail lives.
    """
    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access {active: true})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    WHERE ac.suspendedAt IS NOT NULL
    SET ac.suspendedAt = NULL,
        ac.suspensionReason = NULL

    WITH ac
    OPTIONAL MATCH (ac)-[r:SUSPENDED_BY]->(:User)
    DELETE r
    RETURN ac.uid AS uid
    """
    results, _ = await adb.cypher_query(
        query, {"user_uid": user_uid, "entry_uid": entry_uid}
    )
    return bool(results)


async def access_history(user_uid: str, entry_uid: str) -> list[dict]:
    """Every Access this user has held for this site, newest first.

    Includes the inactive ones — they are the history. `supersededBy` and
    `createdBy` come back as uids rather than nodes so a caller can serialise
    the result without another round trip per row.
    """
    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access)
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (ac)-[:SUPERSEDED_BY]->(sb:User)
    OPTIONAL MATCH (ac)-[:CREATED_BY]->(cb:User)
    RETURN ac.uid AS uid,
           ac.role AS role,
           ac.active AS active,
           ac.createdAt AS createdAt,
           ac.createdByRole AS createdByRole,
           ac.supersededAt AS supersededAt,
           ac.suspendedAt AS suspendedAt,
           ac.suspensionReason AS suspensionReason,
           sb.uid AS supersededBy,
           cb.uid AS createdBy,
           cb.name AS createdByName
    ORDER BY ac.createdAt DESC
    """
    results, meta = await adb.cypher_query(
        query, {"user_uid": user_uid, "entry_uid": entry_uid}
    )
    return [dict(zip(meta, row)) for row in results]
