import logging
from rest_framework import permissions
from access.utils import authorize_api

logger = logging.getLogger(__name__)

class ResponsePermissions(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        logger.debug(f'has_object_permission {request.user.is_authenticated=}')
        logger.debug(f'has_object_permission {obj=}')
        logger.debug(f'has_object_permission {request.user=}')
        endpoint = "survey"
        return authorize_api(endpoint, request)

    def has_permission(self, request, view):
        logger.debug(f'has_permission {request.user.is_authenticated=}')
        logger.debug(f'has_permission {request.user=}')
        endpoint = "survey"
        return authorize_api(endpoint, request)