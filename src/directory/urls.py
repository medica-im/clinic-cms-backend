from django.urls import include, path
from rest_framework import routers
from directory import views

router = routers.DefaultRouter()

app_name = 'directory'

urlpatterns = [
    path(
        '',
        views.DirectoryView.as_view(),
    ),
    path(
        'effector_type_labels/',
        views.EffectorTypeLabel.as_view(),
    ),
    path(
        'timestamps',
        views.TimestampView.as_view(),
    ),
    path(
        'api-auth/',
        include('rest_framework.urls', namespace='rest_framework')
    ),
]
