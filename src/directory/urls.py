from django.urls import include, path, re_path
from tastypie.api import Api
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

v1_api = Api(api_name='v1')
v1_api.register(EffectorResource())
v1_api.register(SituationResource())
v1_api.register(EffectorTypeResource())
v1_api.register(CommuneResource())

app_name = 'directory'

urlpatterns = [
re_path(r'', include(v1_api.urls)),
]