import logging
from time import time_ns

from django.contrib.sites.models import Site
from neomodel import adb
from access.asyncneomodels import (
    Account as AsyncAccount,
    User as AsyncUser,
    Access as AsyncAccess,
    Invitee as AsyncInvitee,
)
from directory.models.agraph import Entry
from facility.models import Organization

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
            return _build_response(user_props, role, jwt)
        except Exception:
            logger.exception("Failed to add Access to existing Neo4j user")
            return None
    else:
        # Case C: brand-new user — create User + Account + Access
        try:
            user_props, role = await _create_user_from_invitee(
                invitee, entry, sub, iss, email, jwt.get("name", "")
            )
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
    invitee, entry, sub: str, iss: str, email: str, name: str
) -> tuple[dict, str]:
    """Create Account, User, and Access nodes from an Invitee.

    Returns (user_properties, role_name).
    """
    # Create Account
    account = await AsyncAccount(sub=sub, iss=iss).save()

    # Create User
    user = await AsyncUser(
        email=email,
        name=name,
        invitee=invitee.uid,
    ).save()

    # Connect User -> Account
    await user.accounts.connect(account)

    # Create Access with the Invitee's role
    access = await AsyncAccess(role=invitee.role).save()

    # Connect User -> Access
    await user.access.connect(access)

    # Connect Access -> Entry
    await access.entry.connect(entry)

    # Connect User as creator of Access
    await access.createdBy.connect(user)

    # Mark the Invitee as redeemed
    invitee.redeemedAt = time_ns() // 1_000_000
    await invitee.save()

    logger.info(
        f"Created Neo4j User {user.uid} from Invitee {invitee.uid} "
        f"with role {invitee.role}"
    )

    return user.__properties__, invitee.role

async def _add_access_to_existing_user(
    user_props: dict, invitee, entry
) -> tuple[dict, str]:
    """Add a new Access node to an already-existing User for a new entry/role.

    Access.createdBy is taken from the Invitee's createdBy relationship
    (i.e. the admin who issued the invitation).
    """
    user = await AsyncUser.nodes.get(uid=user_props["uid"])

    # Inherit the creator from the Invitee
    invitee_creator = await invitee.createdBy.single()

    access = await AsyncAccess(role=invitee.role).save()
    await user.access.connect(access)
    await access.entry.connect(entry)
    if invitee_creator:
        await access.createdBy.connect(invitee_creator)

    invitee.redeemedAt = time_ns() // 1_000_000
    await invitee.save()

    logger.info(
        f"Added Access (role={invitee.role}) to existing User {user.uid} "
        f"from Invitee {invitee.uid}"
    )
    return user.__properties__, invitee.role


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
