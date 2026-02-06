import logging
from django.contrib.auth import get_user_model
from access.models import Role
from workforce.utils import is_staff
from django.http import HttpRequest
from access.models import AccessControl, Endpoint, Role
from rest_framework import permissions
User=get_user_model()

logger = logging.getLogger(__name__)

def get_role_objs():
    roles = dict()
    for role in [
        "superuser", "administrator", "staff", "registered", "anonymous"
    ]:
        try:
            roles[role] = Role.objects.get(name=role)
        except Role.DoesNotExist as e:
            logger.error(f'You must create a Role named {role}.')
            raise e
    return roles

async def async_get_role_objs():
    roles = dict()
    for role in [
        "superuser", "administrator", "staff", "registered", "anonymous"
    ]:
        try:
            roles[role] = await Role.objects.aget(name=role)
        except Role.DoesNotExist as e:
            logger.error(f'You must create a Role named {role}.')
            raise e
    return roles

def get_role(request: HttpRequest)-> Role:
    user = request.user
    roles = get_role_objs()
    if user.is_superuser:
        return roles["superuser"]
    elif is_staff(request):
        return roles["staff"]
    elif user.is_authenticated:
        return roles["registered"]
    else:
        return roles["anonymous"]

async def async_get_role(request: HttpRequest):
    user = request.user
    roles = await async_get_role_objs()
    if user.is_anonymous:
        return roles["anonymous"]
    elif user.is_superuser:
        return roles["superuser"]
    elif is_staff(request):
        return roles["staff"]
    elif user.is_authenticated:
        return roles["registered"]

def authorize_api(endpoint: str, request: HttpRequest):
    # get post put patch delete
    role = get_role(request)
    if request.method in permissions.SAFE_METHODS:
        permission = 1 
    elif request.method == "POST":
        permission = 2
    elif request.method in ["PUT", "PATCH"]:
        permission = 4
    elif request.method == "DELETE":
        permission = 8
    return authorize(endpoint, role, permission)

def authorize(endpoint_name: str, role: Role, permissions: int):
    try:
        endpoint = Endpoint.objects.get(name=endpoint_name)
    except Endpoint.DoesNotExist:
        return False
    try:
        ac = AccessControl.objects.get(endpoint=endpoint, role=role)
    except AccessControl.DoesNotExist:
        return False
    return ac.check_permission(permissions)

def get_access(roles: list[Role]):
    role_names = [role.name for role in roles]
    roles_set=set(role_names)
    if roles_set == set(['anonymous', 'staff', 'administrator', 'superuser']):
        return 'W'
    elif roles_set == set(['staff', 'administrator', 'superuser']):
        return 'M'
    elif roles_set == set(['administrator', 'superuser']):
        return 'A'