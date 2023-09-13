from django.urls import include, path, re_path
from rest_framework import routers
from .views import AccessControlViewSet

router = routers.DefaultRouter()
router.register(r'control', AccessControlViewSet)
#urlpatterns = router.urls

app_name = 'access'

urlpatterns = [
    path('', include(router.urls)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]
