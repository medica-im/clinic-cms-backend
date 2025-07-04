from django.urls import include, path
from rest_framework import routers
from heatwave import views

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
app_name = 'heatwave'

urlpatterns = [
    path(
        'warning/<str:pk>',
        views.heatwave_department.as_view(),
    )
]