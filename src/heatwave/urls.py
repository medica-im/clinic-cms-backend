from django.urls import include, path
from heatwave import views
from rest_framework import routers

router = routers.DefaultRouter()

# Wire up our API using automatic URL routing.
app_name = 'heatwave'


urlpatterns = [
    path(
        'warning/<str:pk>/',
        views.Heatwave.as_view(),
    ),
]