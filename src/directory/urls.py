from django.urls import include, path, re_path
from tastypie.api import Api
from directory.tasty import MessageResource
from directory.views import hello_world


v1_api = Api(api_name='v1')
v1_api.register(MessageResource())

app_name = 'directory'

urlpatterns = [
path('hello-world/', hello_world),
re_path(r'', include(v1_api.urls)),
]