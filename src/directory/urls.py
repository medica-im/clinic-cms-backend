from django.urls import include, path, re_path
from tastypie.api import Api, NamespacedApi
from rest_framework import routers
from directory import views

from directory.tasty.effectors import (
    EffectorResource,
)
from directory.tasty.situations import (
    SituationResource,
)
from directory.tasty.types import (
    EffectorTypeResource,
)
from directory.tasty.communes import (
    CommuneResource,
)
from directory.tasty.fulleffectors import (
    FullEffectorResource,
)
from directory.tasty.carehome import CareHomeResource
from directory.tasty.contacts import ContactResource
from directory.tasty.facilities import FacilityResource

# tastypie
v1_api = NamespacedApi(api_name='v1', urlconf_namespace='directory')
v1_api.register(EffectorResource())
v1_api.register(SituationResource())
v1_api.register(EffectorTypeResource())
v1_api.register(CommuneResource())
v1_api.register(CareHomeResource())
v1_api.register(ContactResource())
v1_api.register(FacilityResource())
v1_api.register(FullEffectorResource())

# DRF
router = routers.DefaultRouter()

app_name = 'directory'

urlpatterns = [
    path(
        '',
        views.DirectoryView.as_view(),
    ),
    path(
        'api-auth/',
        include('rest_framework.urls', namespace='rest_framework')
    ),
    re_path(r'', include(v1_api.urls)),
]