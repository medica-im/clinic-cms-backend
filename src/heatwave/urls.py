from django.urls import include, path
from rest_framework import routers
from heatwave import views

router = routers.DefaultRouter()

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
app_name = 'heatwave'

urlpatterns = [
    path(
        'vigilance/<str:pk>',
        views.heatwave_department.as_view(),
    )
]