from django.urls import include, path, re_path
from rest_framework import routers
from workforce.views import (
    WorkforceLabel,
    WorkforceOccupationViewSet
)

# The `user` route is retired: see tests/test_workforce_user_is_retired.py.
# It served an empty queryset (NetworkEdge has no rows), nothing called it, and
# its serializer was the last reader of the Postgres addressbook.Appointment
# table, which appointments moved off when they went to the graph.
router = routers.DefaultRouter()
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