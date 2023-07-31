import logging
import json
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions

from django.shortcuts import render
from backend.i18n import activate_locale
from access.utils import get_role
from directory.utils import get_directory
from directory.models import Effector
from directory import serializers
from django.http import Http404


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