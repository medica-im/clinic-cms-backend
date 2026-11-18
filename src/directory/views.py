import logging
import json
from django.contrib.sites.shortcuts import get_current_site
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions
from rest_framework.generics import RetrieveAPIView, ListAPIView
from rest_framework.exceptions import NotFound

from backend.i18n import activate_locale
from directory.models import Effector, Directory, Timestamp
from directory import serializers
from django.http import Http404

from directory.utils import get_directory

logger = logging.getLogger(__name__)

from rest_framework.decorators import api_view

@api_view()
def hello_world(request):
    return Response({"message": "Hello, world!"})


class EffectorViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for listing or retrieving users.
    """
    def list(self, request):
        #objects = list(Effector.nodes)
        #data = [e.serialize for e in objects]
        data = json.dumps([u.__dict__ for u in Effector.nodes])
        return Response(data)

    def retrieve(self, request, pk=None):
        return Response()


class TimestampView(APIView):

    def get(self, request):
        site = get_current_site(request)
        dct = {}
        for ts in Timestamp.objects.filter(site=site).all():
            dct[ts.endpoint.name]=ts.timestamp
        return Response(dct)


class DirectoryView(RetrieveAPIView):
    queryset = Directory.objects.all()
    serializer_class = serializers.DirectorySerializer

    def get_object(self):
        from directory.utils import get_directory
        try:
            return get_directory(self.request)
        except Directory.DoesNotExist:
            raise NotFound(detail="Directory not found.", code="not_found")

