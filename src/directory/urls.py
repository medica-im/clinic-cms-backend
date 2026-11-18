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
        'timestamps',
        views.TimestampView.as_view(),
    ),
]
