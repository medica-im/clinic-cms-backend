import logging
from time import time_ns
from uuid import uuid4

from django.contrib.sites.models import Site
from neomodel import adb
from access.asyncneomodels import (
    Account as AsyncAccount,
    User as AsyncUser,
)
from facility.models import Organization
from api.utils import clear_cache

logger = logging.getLogger(__name__)


async def get_or_create_neo4j_user(jwt: dict, site: Site) -> dict | None:
    """Look up or create a Neo4j User from JWT claims.

    Returns a /users/me-shaped response dict, or None to fall through
    to Django auth.
    """
    sub = jwt.get("providerAccountId")
    if not sub:
        return None

    iss = jwt.get("iss", "")
    email = jwt.get("email", "")

    # Get the organization's Entry uid for this site
    entry_uid = await _get_entry_uid(site)
    logger.debug(f"Looking up Neo4j user for sub={sub}, email={email}, entry_uid={entry_uid}")
    if not entry_uid:
        return None

    # 1. Look up existing Account by sub
    result = await _find_user_by_sub(sub, entry_uid)
    if result:
        user_props, role = result
        if role:
            # Case A: user exists and already has Access for this entry
            return _build_response(user_props, role, jwt)
        # Case B: user exists but has no Access for this entry — fall through

    # 2. Look up active Invitee by email + Entry
    if not email:
        if result:
            return _build_response(result[0], None, jwt)
        return None

    try:
        invitee, entry = await _find_invitee(email, entry_uid)
    except LookupError:
        if result:
            return _build_response(result[0], None, jwt)
        return None

    # 3. Create or augment Access from Invitee
    if result:
        # Case B: add a new Access to an existing User
        try:
            user_props, role = await _add_access_to_existing_user(
                result[0], invitee, entry
            )
            await _claim_entries_by_redeem_email(user_props["uid"], email, entry_uid)
            return _build_response(user_props, role, jwt)
        except Exception:
            logger.exception("Failed to add Access to existing Neo4j user")
            return None
    else:
        # Case C: brand-new user — create User + Account + Access
        try:
            user_props, role = await _create_user_from_invitee(
                invitee, sub, iss, email, jwt.get("name", ""),
                entry_uid,
            )
            await _claim_entries_by_redeem_email(user_props["uid"], email, entry_uid)
            return _build_response(user_props, role, jwt)
        except Exception:
            logger.exception("Failed to create Neo4j user from invitee")
            return None


async def _get_entry_uid(site: Site) -> str | None:
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        return None
    if not organization.neomodel_uid:
        return None
    return organization.neomodel_uid.hex


async def _find_user_by_sub(sub: str, entry_uid: str) -> tuple[dict, str] | None:
    """Find an existing User via their Account sub, with role scoped to entry."""
    query = """
    MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
    OPTIONAL MATCH (u)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    RETURN u, ac.role
    """
    results, _ = await adb.cypher_query(
        query, {"sub": sub, "entry_uid": entry_uid}, resolve_objects=True
    )
    logger.debug(f"{results=}")
    if not results:
        return None
    user_node = results[0][0]
    logger.debug(f"{user_node=}")
    role = results[0][1]
    logger.debug(f"{role=}")
    return user_node.__properties__, role


async def _find_invitee(email: str, entry_uid: str):
    """Find an active Invitee by email linked to the organization's Entry.

    Returns (invitee_node, entry_node) or raises LookupError.
    """
    query = """
    MATCH (i:Invitee {active: true})-[:INVITED_TO]->(e:Entry {uid: $entry_uid})
    WHERE toLower(i.email) = toLower($email) AND i.redeemedAt IS NULL
    RETURN i, e
    """
    results, _ = await adb.cypher_query(
        query, {"email": email, "entry_uid": entry_uid}, resolve_objects=True
    )
    if not results:
        raise LookupError("No active invitee found")
    return results[0][0], results[0][1]


async def _create_user_from_invitee(
    invitee, sub: str, iss: str, email: str, name: str,
    entry_uid: str,
) -> tuple[dict, str]:
    """Atomically create Account, User, and Access nodes from an Invitee.

    Uses a single Cypher query to prevent race conditions where concurrent
    logins could create duplicate User nodes for the same email.

    Returns (user_properties, role_name).
    """
    now = time_ns() // 1_000_000
    query = """
    MATCH (i:Invitee {uid: $invitee_uid})
    WHERE i.redeemedAt IS NULL
    SET i.redeemedAt = $now

    WITH i

    MERGE (a:Account {sub: $sub})
    ON CREATE SET a.uid = $account_uid, a.iss = $iss, a.createdAt = $now

    MERGE (u:User {email: $email})
    ON CREATE SET u.uid = $user_uid, u.name = $name,
                  u.invitee = $invitee_uid, u.createdAt = $now

    MERGE (u)-[:HAS_ACCOUNT]->(a)

    WITH u, i
    MATCH (e:Entry {uid: $entry_uid})
    CREATE (ac:Access {uid: $access_uid, role: i.role, active: true, createdAt: $now})
    CREATE (u)-[:HAS_ACCESS]->(ac)
    CREATE (ac)-[:ACCESS_TO]->(e)
    CREATE (ac)-[:CREATED_BY]->(u)

    RETURN u {.*} AS user_props, ac.role AS role
    """
    params = {
        "invitee_uid": invitee.uid,
        "now": now,
        "sub": sub,
        "iss": iss,
        "email": email,
        "name": name,
        "entry_uid": entry_uid,
        "account_uid": uuid4().hex,
        "user_uid": uuid4().hex,
        "access_uid": uuid4().hex,
    }
    results, _ = await adb.cypher_query(query, params)
    if not results:
        raise RuntimeError(
            f"Invitee {invitee.uid} was already redeemed (concurrent request)"
        )

    user_props = results[0][0]
    role = results[0][1]

    logger.info(
        f"Created Neo4j User {user_props.get('uid')} from Invitee {invitee.uid} "
        f"with role {role}"
    )

    return user_props, role

async def _add_access_to_existing_user(
    user_props: dict, invitee, entry
) -> tuple[dict, str]:
    """Atomically add a new Access node to an existing User for a new entry/role.

    Uses a single Cypher query to prevent race conditions where concurrent
    logins could create duplicate Access nodes for the same User+Entry.

    Access.createdBy is taken from the Invitee's createdBy relationship
    (i.e. the admin who issued the invitation).
    """
    now = time_ns() // 1_000_000
    query = """
    MATCH (i:Invitee {uid: $invitee_uid})
    WHERE i.redeemedAt IS NULL
    SET i.redeemedAt = $now

    WITH i
    MATCH (u:User {uid: $user_uid})
    MATCH (e:Entry {uid: $entry_uid})

    CREATE (ac:Access {uid: $access_uid, role: i.role, active: true, createdAt: $now})
    CREATE (u)-[:HAS_ACCESS]->(ac)
    CREATE (ac)-[:ACCESS_TO]->(e)

    WITH u, ac, i
    OPTIONAL MATCH (i)-[:CREATED_BY]->(creator:User)
    FOREACH (_ IN CASE WHEN creator IS NOT NULL THEN [1] ELSE [] END |
        CREATE (ac)-[:CREATED_BY]->(creator)
    )

    RETURN u {.*} AS user_props, ac.role AS role
    """
    params = {
        "invitee_uid": invitee.uid,
        "now": now,
        "user_uid": user_props["uid"],
        "entry_uid": entry.uid,
        "access_uid": uuid4().hex,
    }
    results, _ = await adb.cypher_query(query, params)
    if not results:
        raise RuntimeError(
            f"Invitee {invitee.uid} was already redeemed (concurrent request)"
        )

    user_props = results[0][0]
    role = results[0][1]

    logger.info(
        f"Added Access (role={role}) to existing User {user_props.get('uid')} "
        f"from Invitee {invitee.uid}"
    )
    return user_props, role


async def get_neo4j_role(jwt: dict, site: Site) -> str|None:
    """Resolve role from Neo4j Access graph. Returns role name string or None."""
    try:
        sub = jwt.get("providerAccountId")
        logger.debug(f"{sub=}")
    except AttributeError:
        return
    if not sub:
        return
    entry_uid = await _get_entry_uid(site)
    logger.debug(f"{entry_uid=}")
    if not entry_uid:
        return
    result = await _find_user_by_sub(sub, entry_uid)
    if result:
        _, role = result
        return role

def normalize_neo4j_role(role: str|None) -> str:
    if role == "registered" or role is None:
        return "anonymous"
    elif role == "superuser":
        return "administrator"
    else:
        return role

async def get_neo4j_user(jwt: dict) -> AsyncUser | None:
    """Return the Neo4j User node for the requesting user, or None."""
    sub = jwt.get("providerAccountId")
    if not sub:
        return None
    try:
        account = await AsyncAccount.nodes.get(sub=sub)
    except AsyncAccount.DoesNotExist:
        return None
    return await account.user.single()


async def _claim_entries_by_redeem_email(
    user_uid: str, email: str, entry_uid: str
) -> None:
    """Claim Entry ownership when redeemEmail matches the user's email.

    Finds all entries in the site's directories where redeemEmail matches,
    creates OWNED_BY relationships, and removes the redeemEmail property.
    """
    query = """
    MATCH (org_entry:Entry {uid: $entry_uid})<-[:HAS_ENTRY]-(d:Directory)-[:HAS_ENTRY]->(e:Entry)
    WHERE toLower(e.redeemEmail) = toLower($email)
    WITH e
    MATCH (u:User {uid: $user_uid})
    CREATE (e)-[:OWNED_BY]->(u)
    REMOVE e.redeemEmail
    RETURN e.uid AS claimed_uid
    """
    try:
        results, _ = await adb.cypher_query(
            query,
            {"entry_uid": entry_uid, "email": email, "user_uid": user_uid},
        )
        if results:
            for row in results:
                logger.info(f"Claimed Entry {row[0]} ownership for User {user_uid}")
            try:
                org = await Organization.objects.select_related('site').aget(
                    neomodel_uid=entry_uid
                )
                await clear_cache("v2:entries", site=org.site)
            except Organization.DoesNotExist:
                logger.warning(f"Could not find Organization for entry_uid={entry_uid} to clear cache")
    except Exception:
        logger.exception(
            f"Failed to claim entries by redeemEmail for User {user_uid}"
        )


def _build_response(user_props: dict, role: str | None, jwt: dict) -> dict:
    return {
        "uid": user_props.get("uid"),
        "name": user_props.get("name"),
        "email": user_props.get("email"),
        "picture": jwt.get("picture"),
        "role": role,
        "gender": None,
        "effector": None,
        "full_name": user_props.get("name"),
    }
