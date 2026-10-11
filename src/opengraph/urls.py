from django.urls import include, path
from rest_framework import routers
from opengraph import views

router = routers.DefaultRouter()

# Wire up our API using automatic URL routing.
app_name = 'opengraph'

urlpatterns = [
    path(
        '',
        views.OpenGraphView.as_view(),
    ),
]