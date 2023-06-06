import logging
from rest_framework import viewsets
from rest_framework.generics import RetrieveAPIView
from facility.models import Organization, Category
from addressbook.models import Contact
from facility.serializers import (
    OrganizationSerializer,
    CategorySerializer,
    ContactSerializer,
)
from backend.i18n import activate_locale
from rest_framework.exceptions import NotFound

logger=logging.getLogger(__name__)


class OrganizationView(RetrieveAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_object(self):
        language = self.kwargs.get('language', None)
        activate_locale(language, self.request)
        try:
            return Organization.objects.get(site=self.request.site)
        except Organization.DoesNotExist:
            raise NotFound(detail="Organization not found.", code="not_found")


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ContactViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer  