import logging
import os
from typing import TypedDict
from access.models import AccessControl, Endpoint, Role
from accounts.models import User, Role as AccountRole
from django.contrib.sites.models import Site
from fastapi import Request, HTTPException, status
from api.utils import get_site_from_request
from fastapi_nextauth_jwt import NextAuthJWT
from django.db.models import F
from api.neo4j_auth import get_neo4j_role
from access.asyncneomodels import User as Neo4jUser

logger = logging.getLogger(__name__)

auth_secret=os.getenv("AUTH_SECRET")
if auth_secret:
    JWT = NextAuthJWT(
        secret=auth_secret,
        csrf_prevention_enabled=False
    )

async def get_user(jwt: dict) -> User|None:
    try:
        email = jwt['email']
    except (AttributeError,TypeError,):
        return None
    try:
        return await User.objects.aget(email__iexact=email)
    except User.DoesNotExist as e:
        return None

async def get_role_objs() -> dict[str, Role]:
    roles = dict()
    for role in [
        "superuser", "administrator", "staff", "registered", "anonymous"
    ]:
        try:
            roles[role] = await Role.objects.aget(name=role)
        except Role.DoesNotExist:
            error_msg = f'You must create a Role named {role}.'
            logger.error(error_msg)
            raise Role.DoesNotExist(error_msg)
    return roles

async def get_role(user: User|None, site: Site) -> Role:
    roles_dct = await get_role_objs()
    if not user:
        return roles_dct["anonymous"]
    if user.is_superuser:
        return roles_dct["superuser"]
    try:
        account_role = await AccountRole.objects.prefetch_related('role').aget(user=user, site=site, active=True)
        return account_role.role
    except AccountRole.DoesNotExist as e:
        logger.warning(f"No active role found for user {user} on site {site.domain}. Defaulting to anonymous.")
        return roles_dct["anonymous"]
    except AccountRole.MultipleObjectsReturned as e:
        logger.error(e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Insufficient permissions"
        )

class RoleType(TypedDict):
    role_name: str
    directory: str|None

def _method_to_permission(method: str) -> int:
    if method == "GET":
        return 1
    elif method == "POST":
        return 2
    elif method in ("PUT", "PATCH"):
        return 4
    elif method == "DELETE":
        return 8
    return 0

async def is_user_in_authorized_list(jwt: dict, users: list[Neo4jUser]) -> bool:
    sub = jwt.get("providerAccountId")
    if not sub:
        return False
    for user in users:
        accounts = await user.accounts.all()
        if any(account.sub == sub for account in accounts):
            logger.debug(
                f"Object permission granted: {user} with sub={sub} is in authorized users list"
            )
            return True
    return False

async def may_authorize_api(
    endpoint: str,
    request: Request,
    jwt: dict,
    users: list[Neo4jUser]|None=None,
    method: str|None=None,
) -> bool:
    """
    Whether this caller may perform this action — the question, not the gate.

    `method` overrides the permission the request's own verb would imply, for
    endpoints that ask about an action rather than perform it: a GET answering
    "may this user edit?" has to be judged as a PUT, or it would check read
    access and answer yes to everyone.
    """
    logger.debug(f"{request.method=}")
    site = await get_site_from_request(request)
    permission = _method_to_permission(method or request.method)

    # Object-level permission: check if the requesting user is in the authorized list
    if users and jwt:
        if await is_user_in_authorized_list(jwt, users):
            return True

    # Try Neo4j first
    neo4j_role_name = await get_neo4j_role(jwt, site)
    logger.debug(f"{neo4j_role_name=}")
    if neo4j_role_name:
        roles_dct = await get_role_objs()
        role = roles_dct.get(neo4j_role_name)
        if role:
            logger.debug(f"Neo4j auth: {site=} {role=}")
            return await may_authorize(endpoint, role, permission)

    # Django fallback (existing behavior)
    user = await get_user(jwt)
    role = await get_role(user, site)
    logger.debug(f"Django auth: {site=} {user=} {role=}")
    return await may_authorize(endpoint, role, permission)


async def authorize_api(
    endpoint: str,
    request: Request,
    jwt: dict,
    users: list[Neo4jUser]|None=None,
    method: str|None=None,
):
    """Enforcing form of may_authorize_api: raises 403 instead of returning False."""
    if not await may_authorize_api(endpoint, request, jwt, users, method):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return True

async def may_authorize(endpoint_name: str, role: Role, permissions: int) -> bool:
    """
    Whether this role holds these permissions on this endpoint.

    Answers with a boolean so callers that need to *ask* about a permission —
    to decide whether to offer a control, say — do not have to catch the
    exception raised by enforcement. Catching it would also swallow genuine
    faults: a missing Endpoint or AccessControl row is a broken configuration,
    not a user who lacks rights, and reporting the two the same way hides it.
    """
    try:
        endpoint = await Endpoint.objects.aget(name=endpoint_name)
    except Endpoint.DoesNotExist:
        logger.error(f"no Endpoint row named {endpoint_name!r}; refusing")
        return False
    try:
        ac = await AccessControl.objects.aget(endpoint=endpoint, role=role)
    except AccessControl.DoesNotExist:
        logger.error(f"no AccessControl for {endpoint_name!r} and role {role!r}; refusing")
        return False
    return await ac.async_check_permission(permissions)


async def authorize(endpoint_name: str, role: Role, permissions: int):
    """Enforcing form of may_authorize: raises 403 instead of returning False."""
    if not await may_authorize(endpoint_name, role, permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )

async def verify_user_access(jwt: dict, entry_uid: str):
    """Verify the requesting user has an active Access for the given Entry."""
    sub = jwt.get("providerAccountId")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No account identifier in JWT"
        )
    query = """
    MATCH (a:Account {sub: $sub})<-[:HAS_ACCOUNT]-(u:User)
          -[:HAS_ACCESS]->(ac:Access {active: true})
          -[:ACCESS_TO]->(e:Entry {uid: $entry_uid})
    RETURN ac.role
    """
    from neomodel import adb
    results, _ = await adb.cypher_query(
        query, {"sub": sub, "entry_uid": entry_uid}
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this entry"
        )


def check_cookie_jwt(request: Request):
    """The caller's identity, from a session cookie or a clone token.

    Widened for cross-instance cloning. Every read endpoint takes its identity
    through this one dependency and everything downstream — authorize_api,
    get_neo4j_role, _find_user_by_sub — reads only `providerAccountId` and
    `email`. So accepting a second credential *here* lets /entries and
    /fullentries serve another deployment's clone request with their own
    authorization intact, and without touching a single router.

    Cookie first: a browser on this instance is the ordinary case, and a request
    carrying both should behave as the session it already has.
    """
    https_cookie = request.cookies.get('__Secure-authjs.session-token')
    logger.debug(f"{https_cookie=}")
    http_cookie = request.cookies.get('authjs.session-token')
    logger.debug(f"{http_cookie=}")
    if  http_cookie or https_cookie:
        return JWT(request)
    return clone_token_jwt(request)


def clone_token_jwt(request: Request):
    """Identity from a clone export token, shaped like the NextAuth JWT.

    Returns None when there is no token, so an anonymous request stays
    anonymous. A token that is present but bad raises 401 rather than falling
    through to anonymous: a caller who meant to authenticate and failed should
    be told, not quietly served the public view.

    The claims are stashed on request.state for the scope check in
    api.routers.clone, which is the only place that needs to know *which*
    entries this token may read.
    """
    from api.serializers.clone import token as clone_token

    raw = clone_token.bearer(request)
    if not raw:
        return None
    claims = clone_token.read(raw, request_host=request.url.hostname)
    request.state.clone_claims = claims
    # Only the two fields anything downstream reads. Deliberately not a full
    # session: this identity may read, and only what the token scopes it to.
    return {"providerAccountId": claims.sub, "email": ""}

def normalize_role(roles, directory):
    for r in roles:
        if directory.name == r["directory"]:
            role = r["role_name"]
            if role == "registered":
                return "anonymous"
            return role
    return "anonymous"