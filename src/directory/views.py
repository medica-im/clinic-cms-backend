import logging
import json
from common.utils import timeit
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
from django.core.cache import cache

from accounts.models import GrammaticalGender
from directory.models.core import Label

from directory.utils import (
    get_directory,
    get_ttl,
    set_timestamp,
)

logger = logging.getLogger(__name__)

TTL: int = 60

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
        try:
            return Directory.objects.get(site=self.request.site)
        except Directory.DoesNotExist:
            raise NotFound(detail="Directory not found.", code="not_found")


def get_effector_type_labels(language: str):
    dictionary = {}
    node_label_set = set([uid.hex for uid in Label.objects.values_list("uid", flat=True)])
    for uid in node_label_set:
        dictionary[uid] = {
            "S": {
                "F": None,
                "M": None,
                "N": None,
            },
            "P": {
                "F": None,
                "M": None,
                "N": None,
            }
        }
        try:
            F = GrammaticalGender.objects.get(name="feminine")
            M = GrammaticalGender.objects.get(name="masculine")
            N = GrammaticalGender.objects.get(name="neutral")
        except GrammaticalGender.DoesNotExist as e:
            logger.error(f"Missing GrammaticalGender object: {e}")
        for Num in ["S", "P"]:
            for G in [F, M, N]:
                try:
                    l = Label.objects.get(
                        uid=uid,
                        gender=G,
                        grammatical_number=Num,
                        language=language
                    )
                    dictionary[uid][Num][G.code]=l.label
                except Label.DoesNotExist:
                    continue
    return dictionary


class EffectorTypeLabel(APIView):
    """
    Return a dictionary of all labels.
    """
    @timeit
    def get(self, request, format=None):
        """
        Return a dictionary of all labels.
        """
        directory = get_directory(self.request)
        language = directory.site.organization.language
        endpoint = f"v1:effector_type_labels"
        cache_key= f"{endpoint}:{language}"
        cached = cache.get(cache_key)
        if cached:
            logger.warning(f"*** Using cache with key {cache_key} ***")
            return Response(cached)
        else:
            logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
            value = get_effector_type_labels(language)
            timeout = get_ttl(endpoint, request) or TTL
            logger.debug(f"{timeout=}")
            cache.set(
                cache_key,
                value,
                timeout=timeout
            )
            set_timestamp(endpoint, request)
            return Response(value)