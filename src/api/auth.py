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
    email = jwt['email']
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
    except AccountRole.DoesNotExist:
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

async def get_role_from_jwt(jwt: dict)->list[RoleType]:
    anon: RoleType = {"role_name": "anonymous", "directory": None}
    if not jwt:
        return [anon]
    else:
        email = jwt['email']
        try:
            user = await User.objects.aget(email__iexact=email)
        except User.DoesNotExist:
            return [anon]
        roles: list[RoleType] = []
        async for r in AccountRole.objects.filter(user=user).values(role_name=F("role__name"),directory=F("site__directory__name")):
            roles.append(r)
        logger.debug(f"{roles=}")
        return roles

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

async def authorize_api(endpoint: str, request: Request, jwt: dict, users: list[Neo4jUser]|None=None):
    logger.debug(f"{request.method=}")
    site = await get_site_from_request(request)
    permission = _method_to_permission(request.method)

    # Object-level permission: check if the requesting user is in the authorized list
    if users and jwt:
        sub = jwt.get("providerAccountId")
        if sub:
            for user in users:
                accounts = await user.accounts.all()
                if any(account.sub == sub for account in accounts):
                    logger.debug(
                        f"Object permission granted: {user} with sub={sub} is in authorized users list"
                    )
                    return True

    # Try Neo4j first
    neo4j_role_name = await get_neo4j_role(jwt, site)
    logger.debug(f"{neo4j_role_name=}")
    if neo4j_role_name:
        roles_dct = await get_role_objs()
        role = roles_dct.get(neo4j_role_name)
        if role:
            logger.debug(f"Neo4j auth: {site=} {role=}")
            return await authorize(endpoint, role, permission)

    # Django fallback (existing behavior)
    user = await get_user(jwt)
    role = await get_role(user, site)
    logger.debug(f"Django auth: {site=} {user=} {role=}")
    return await authorize(endpoint, role, permission)

async def authorize(endpoint_name: str, role: Role, permissions: int):
    try:
        endpoint = await Endpoint.objects.aget(name=endpoint_name)
    except Endpoint.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    try:
        ac = await AccessControl.objects.aget(endpoint=endpoint, role=role)
    except AccessControl.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    if not await ac.async_check_permission(permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )

def check_cookie_jwt(request: Request):
    http_cookie = request.cookies.get('__Secure-authjs.session-token')
    logger.debug(f"{http_cookie=}")
    https_cookie = request.cookies.get('authjs.session-token')
    logger.debug(f"{https_cookie=}")
    if  http_cookie or https_cookie:
        return JWT(request)
    else:
        return

def normalize_role(roles, directory):
    for r in roles:
        if directory.name == r["directory"]:
            role = r["role_name"]
            if role == "registered":
                return "anonymous"
            elif role == "superuser":
                return "administrator"
            else:
                return role
    return "anonymous"