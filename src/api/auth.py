import logging
import os
from access.models import Role
from workforce.utils import is_staff
from django.http import HttpRequest
from access.models import AccessControl, Endpoint, Role
from rest_framework import permissions
from accounts.models import User
from django.contrib.sites.models import Site
from fastapi import Request, HTTPException, status
from api.utils import get_site_from_request
from fastapi_nextauth_jwt import NextAuthJWT

logger = logging.getLogger(__name__)

auth_secret=os.getenv("AUTH_SECRET")
if auth_secret:
    JWT = NextAuthJWT(secret=auth_secret)

async def get_user(jwt: dict) -> User|None:
    email = jwt['email']
    try:
        return await User.objects.aget(email=email)
    except User.DoesNotExist as e:
        return None

async def get_role_objs():
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
    roles = await get_role_objs()
    if not user:
        return roles["anonymous"]
    elif user.is_superuser:
        return roles["superuser"]
    elif user.site==site:
        return roles["staff"]
    else:
        return roles["registered"]

async def authorize_api(endpoint: str, request: Request, jwt: dict):
    # get post put patch delete
    logger.debug(f"{request.method=}")
    site = await get_site_from_request(request)
    logger.debug(site)
    user = await get_user(jwt)
    logger.debug(user)
    role = await get_role(user, site)
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
        endpoint = Endpoint.objects.aget(name=endpoint_name)
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
    