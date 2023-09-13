import logging
from rest_framework import permissions
from access.utils import authorize_api
from addressbook.models import Contact

logger = logging.getLogger(__name__)

class ProfilePermissions(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        # All permissions for the owner of the profile.
        logger.debug(f'{request.user.is_authenticated=}')
        logger.debug(obj)
        logger.debug(f'{obj.contact.user=}')
        logger.debug(f'{request.user}')
        logger.debug(f'{obj.contact.user == request.user=}')
        if obj.contact.user == request.user:
            return True
        endpoint = "profile"
        return authorize_api(endpoint, request)

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        contact_id = request.data.get("contact", None)
        logger.debug(f'{contact_id}');
        if contact_id:
            try:
                user = Contact.objects.get(id=contact_id).user
            except Contact.DoesNotExist:
                user = None
            if user == request.user:
                return True
        endpoint = "profile"
        return authorize_api(endpoint, request)

class ObjectPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.contact.user == request.user:
            return True