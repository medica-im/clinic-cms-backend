from django.urls import include, path, re_path
from tastypie.api import Api, NamespacedApi

from directory.tasty.effectors import (
    EffectorResource,
    SituationResource,
)
from directory.tasty.types import (
    EffectorTypeResource,
)
from directory.tasty.communes import (
    CommuneResource,
)
from directory.tasty.carehome import CareHomeResource
from directory.tasty.contacts import ContactResource

v1_api = NamespacedApi(api_name='v1', urlconf_namespace='directory')
v1_api.register(EffectorResource())
v1_api.register(SituationResource())
v1_api.register(EffectorTypeResource())
v1_api.register(CommuneResource())
v1_api.register(CareHomeResource())
v1_api.register(ContactResource())

app_name = 'directory'

urlpatterns = [
re_path(r'', include(v1_api.urls)),
]