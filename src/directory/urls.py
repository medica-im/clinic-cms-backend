from django.urls import include, path, re_path
from tastypie.api import Api
from directory.tasty.effectors import (
    MessageResource,
    SituationResource,
)
from directory.tasty.types import (
    EffectorTypeResource
)

v1_api = Api(api_name='v1')
v1_api.register(MessageResource())
v1_api.register(SituationResource())
v1_api.register(EffectorTypeResource())

app_name = 'directory'

urlpatterns = [
re_path(r'', include(v1_api.urls)),
]