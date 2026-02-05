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

async def authorize_api(endpoint: str, request: Request, jwt: dict):
    # get post put patch delete
    logger.debug(f"{request.method=}")
    site = await get_site_from_request(request)
    logger.debug(site)
    user = await get_user(jwt)
    logger.debug(user)
    role = await get_role(user, site)
    logger.debug(f"{site=} {user=} {role=}")
    permission = 0
    if request.method == "GET":
        permission = 1 
    elif request.method == "POST":
        permission = 2
    elif request.method in ["PUT", "PATCH"]:
        permission = 4
    elif request.method == "DELETE":
        permission = 8
    return await authorize(endpoint, role, permission)

async def authorize(endpoint_name: str, role: Role, permissions: int):
    try:
        endpoint = await Endpoint.objects.aget(name=endpoint_name)
    except Endpoint.DoesNotExist:
        return False
    try:
        ac = await AccessControl.objects.aget(endpoint=endpoint, role=role)
    except AccessControl.DoesNotExist:
        return False
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