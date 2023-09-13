import logging

from addressbook.models import Profile, App
from addressbook.api.serializers import ProfileSerializer, AppSerializer
from facility.utils import get_organization
from addressbook.api.permissions import ProfilePermissions
from rest_framework import generics, status, viewsets
from rest_framework.response import Response

logger = logging.getLogger(__name__)

class ProfileList(generics.ListCreateAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [ProfilePermissions]

    def perform_create(self, serializer):
        changed_by = self.request.user
        organization = get_organization(self.request)
        roles = self.request.data.get("roles", None)
        text = self.request.data.get("text", None)
        if roles:
            serializer.save(
                changed_by=changed_by,
                text=text,
                roles=roles,
                organization=organization
            )
        else:
            serializer.save(
                changed_by=changed_by,
                text=text,
                organization=organization
            )

class ProfileDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [ProfilePermissions]

    def perform_update(self, serializer):
        changed_by = self.request.user
        organization = get_organization(self.request)
        logger.debug(f'{organization=}')
        instance = self.get_object()  # instance before update
        roles = self.request.data.get("roles", None) or instance.roles.all()
        text = self.request.data.get("text", None)
        if text is None:
            text=instance.text
        #serializer.save(changed_by=changed_by)
        #profile_id = serializer.data.get('id')
        #profile_obj = Profile.objects.get(id = profile_id)
        #profile_obj.organization = organization
        serializer.save(
            changed_by=changed_by,
            text=text,
            roles=roles,
            organization=organization
        )


class AppViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for viewing accounts.
    """
    queryset = App.objects.all()
    serializer_class = AppSerializer