from django.urls import include, path, re_path
from rest_framework import routers
from workforce.views import (
    WorkforceUserViewSet,
    WorkforceLabel,
    WorkforceOccupationViewSet
)

router = routers.DefaultRouter()
router.register(
    r'user',
    WorkforceUserViewSet,
    basename="User"
)
router.register(
    r'occupation',
    WorkforceOccupationViewSet,
    basename="Occupation"
)

app_name = 'workforce'

urlpatterns = [
    path('dictionary/', WorkforceLabel.as_view()),
    path('', include(router.urls)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]