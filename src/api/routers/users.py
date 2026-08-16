import logging
from typing import Annotated

from fastapi import APIRouter, Request, Depends, status, HTTPException
from neomodel import adb

from api.types.user import (
    User,
    AccountOut,
    AccessOut,
    AccessHistoryOut,
    RoleChangeIn,
    SuspensionIn,
)
from api.auth import JWT, check_cookie_jwt, authorize_api
from api.neo4j_auth import get_neo4j_user
from api.utils import get_site_from_request
from access import access_graph
from access.role_change import Decision, may_change_role, may_suspend
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()

# A refusal is either a judgement about the caller or a fact about the data.
# See access/role_change.py for why the two must not be collapsed.
_STATUS = {
    Decision.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    Decision.CONFLICT: status.HTTP_409_CONFLICT,
}

_DETAIL = {
    Decision.FORBIDDEN: "Insufficient permissions",
    Decision.CONFLICT: "This change cannot be made",
}


def _refuse(decision: Decision, detail: str | None = None):
    raise HTTPException(
        status_code=_STATUS[decision],
        detail=detail or _DETAIL[decision],
    )


async def _entry_uid_for_request(request: Request) -> str:
    """The uid of the Entry every Access on this site hangs from.

    A role is always a role *somewhere*: the same person can be staff on one
    site and an administrator on another, and the Entry is what scopes them
    apart. Resolving it wrongly would read or write the wrong site's access.
    """
    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    return str(organization.neomodel_uid.hex)


async def _actor_and_target(request: Request, jwt: dict, user_uid: str):
    """Resolve who is asking, who they are acting on, and both their accesses.

    The caller's role is read from the graph rather than taken from the JWT:
    the JWT says who somebody is, not what they may do, and a token issued
    before a demotion would otherwise still carry the old privileges.
    """
    entry_uid = await _entry_uid_for_request(request)

    # No JWT at all is a signed-out caller, not an error: they are resolved to
    # no identity and judged as anonymous by the rules.
    actor = await get_neo4j_user(jwt) if jwt else None
    actor_uid = actor.uid if actor else None
    actor_access = (
        await access_graph.get_access(actor_uid, entry_uid) if actor_uid else None
    )
    # No Access here means no role on this site, which is exactly what an
    # anonymous visitor has — so the rules judge them as one.
    actor_role = actor_access["role"] if actor_access else "anonymous"

    target_access = await access_graph.get_access(user_uid, entry_uid)
    if not target_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with uid {user_uid} has no access on this site",
        )

    return {
        "entry_uid": entry_uid,
        "actor_uid": actor_uid,
        "actor_role": actor_role,
        "actor_suspended": bool(actor_access and actor_access["suspendedAt"]),
        "target_access": target_access,
        "actor_is_target": actor_uid is not None and actor_uid == user_uid,
    }


@router.patch("/users/{user_uid}/role")
async def change_user_role(
    user_uid: str,
    payload: RoleChangeIn,
    request: Request,
    # Optional on purpose. The mandatory dependency turns a signed-out caller
    # away with a 401 before any rule runs, which says "authenticate first" —
    # an invitation to retry — where the truthful answer is that no amount of
    # signing in as nobody permits this. The rules below judge them as the
    # anonymous visitor they are, and refuse with 403.
    jwt: Annotated[dict, Depends(check_cookie_jwt)],
) -> AccessOut:
    """Grant a user a different role on this site.

    The refusals live in access/role_change.py, and they are enforced here
    rather than only in the page that offers the control: a hidden button
    proves nothing about a request made directly.

    Note there is no authorize_api call. The AccessControl table answers "may
    this role write to this endpoint at all", which cannot express any of the
    rules that matter here — they depend on the target's role and on who the
    actor is, not just on the actor's role. Asking it as well would add a
    second, coarser gate that only ever refuses people the rules below already
    judge correctly.
    """
    ctx = await _actor_and_target(request, jwt, user_uid)
    target_access = ctx["target_access"]

    last_superuser = (
        target_access["role"] == "superuser"
        and await access_graph.count_superusers(ctx["entry_uid"]) <= 1
    )

    decision = may_change_role(
        actor_role=ctx["actor_role"],
        target_role=target_access["role"],
        granted=payload.role,
        actor_is_target=ctx["actor_is_target"],
        target_suspended=bool(target_access["suspendedAt"]),
        actor_suspended=ctx["actor_suspended"],
        last_superuser=last_superuser,
    )
    if decision is not Decision.ALLOWED:
        _refuse(decision)

    try:
        await access_graph.supersede_access(
            user_uid=user_uid,
            entry_uid=ctx["entry_uid"],
            granted=payload.role,
            actor_uid=ctx["actor_uid"],
            actor_role=ctx["actor_role"],
        )
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )

    access = await access_graph.get_access(user_uid, ctx["entry_uid"])
    return AccessOut.model_validate(access)


@router.post("/users/{user_uid}/suspension")
async def suspend_user(
    user_uid: str,
    payload: SuspensionIn,
    request: Request,
    jwt: Annotated[dict, Depends(check_cookie_jwt)],
) -> AccessOut:
    """Suspend a user's access, keeping their identity and their role.

    The access stays active and keeps its role. A suspended administrator has
    to remain distinguishable from an ordinary user, or the dashboard has
    nothing to explain and the restore has nothing to restore.
    """
    ctx = await _actor_and_target(request, jwt, user_uid)

    decision = may_suspend(ctx["actor_role"], ctx["actor_is_target"])
    if decision is not Decision.ALLOWED:
        _refuse(decision)

    suspended = await access_graph.suspend_access(
        user_uid=user_uid,
        entry_uid=ctx["entry_uid"],
        actor_uid=ctx["actor_uid"],
        reason=payload.reason,
    )
    if not suspended:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with uid {user_uid} has no access to suspend",
        )

    access = await access_graph.get_access(user_uid, ctx["entry_uid"])
    return AccessOut.model_validate(access)


@router.delete("/users/{user_uid}/suspension")
async def restore_user(
    user_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(check_cookie_jwt)],
) -> AccessOut:
    """Lift a suspension. Restoring is the same privilege as suspending."""
    ctx = await _actor_and_target(request, jwt, user_uid)

    decision = may_suspend(ctx["actor_role"], ctx["actor_is_target"])
    if decision is not Decision.ALLOWED:
        _refuse(decision)

    await access_graph.restore_access(user_uid, ctx["entry_uid"])

    access = await access_graph.get_access(user_uid, ctx["entry_uid"])
    return AccessOut.model_validate(access)


@router.get("/users/{user_uid}/access-history")
async def get_access_history(
    user_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> list[AccessHistoryOut]:
    """Every role this user has held on this site, newest first.

    Reading the trail is an ordinary privileged read, so it goes through the
    AccessControl table like the rest of this router — unlike the writes above,
    nothing about it depends on the target.
    """
    await authorize_api("users_v2", request, jwt)

    entry_uid = await _entry_uid_for_request(request)
    history = await access_graph.access_history(user_uid, entry_uid)
    return [AccessHistoryOut.model_validate(row) for row in history]


@router.get("/users")
async def get_users(
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> list[User]:
    await authorize_api("users_v2", request, jwt)

    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    entry_uid = str(organization.neomodel_uid.hex)

    query = """
    MATCH (u:User)-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (u)-[:HAS_ACCOUNT]->(a:Account)
    RETURN u, collect(DISTINCT a) AS accounts, collect(DISTINCT ac) AS accesses
    """
    results, _ = await adb.cypher_query(
        query, {"entry_uid": entry_uid}, resolve_objects=True
    )
    user_list = []
    for row in results:
        (user_node, [account_nodes], [access_nodes]) = row
        accounts = [
            AccountOut.model_validate(a.__dict__)
            for a in account_nodes
        ]
        accesses = [
            AccessOut.model_validate(ac.__dict__)
            for ac in access_nodes
        ]
        user_data = user_node.__properties__
        user_data["accounts"] = accounts
        user_data["access"] = accesses
        user_list.append(User.model_validate(user_data))
    return user_list


@router.get("/users/{user_uid}")
async def get_user(
    user_uid: str,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
) -> User:
    await authorize_api("users_v2", request, jwt)

    site = await get_site_from_request(request)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found for this site",
        )

    if not organization.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization does not have a neomodel_uid",
        )

    entry_uid = str(organization.neomodel_uid.hex)

    query = """
    MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(ac:Access {active: true})-[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    OPTIONAL MATCH (u)-[:HAS_ACCOUNT]->(a:Account)
    RETURN u, collect(DISTINCT a) AS accounts, collect(DISTINCT ac) AS accesses
    """
    results, _ = await adb.cypher_query(
        query, {"user_uid": user_uid, "entry_uid": entry_uid}, resolve_objects=True
    )

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with uid {user_uid} not found for this site",
        )
    logger.debug(f"{results=}")
    user_node, [account_nodes], [access_nodes] = results[0]

    accounts = [
        AccountOut.model_validate(a.__properties__)
        for a in account_nodes
    ]
    accesses = [
        AccessOut.model_validate(ac.__properties__)
        for ac in access_nodes
    ]

    user_data = user_node.__properties__
    user_data["accounts"] = accounts
    user_data["access"] = accesses
    return User.model_validate(user_data)
