import logging
import json
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions
from rest_framework.generics import RetrieveAPIView
from rest_framework.exceptions import NotFound

from django.shortcuts import render
from backend.i18n import activate_locale
from access.utils import get_role
from directory.utils import get_directory, effector_types
from directory.models import Effector, Directory
from directory import serializers
from django.http import Http404

from accounts.models import GrammaticalGender
from directory.models.core import Label


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


class DirectoryView(RetrieveAPIView):
    queryset = Directory.objects.all()
    serializer_class = serializers.DirectorySerializer

    def get_object(self):
        try:
            return Directory.objects.get(site=self.request.site)
        except Directory.DoesNotExist:
            raise NotFound(detail="Directory not found.", code="not_found")


class EffectorTypeLabel(APIView):
    """
    Return a dictionary of all labels.
    """
    def get(self, request, format=None):
        """
        Return a dictionary of all labels.
        """
        lang = self.request.query_params.get('lang')
        activate_locale(lang,self.request)
        directory = get_directory(self.request)
        language = lang or directory.site.organization.language
        uids=effector_types(directory)
        node_has_label=[
            uid.hex for uid in Label.objects.values_list("uid", flat=True)
        ]
        logger.debug(f'{node_has_label=}')
        node_label_set = set()
        for uid in uids:
            if uid in node_has_label:
                node_label_set.add(uid)
        logger.debug(f'{node_label_set=}')
        dictionary = {}
        for uid in node_label_set:
            dictionary[uid] = {
                "S": {
                    "F": None,
                    "M": None,
                },
                "P": {
                    "F": None,
                    "M": None,
                }
            }
            try:
                F = GrammaticalGender.objects.get(name="feminine")
                M = GrammaticalGender.objects.get(name="masculine")
            except GrammaticalGender.DoesNotExist as e:
                logger.error(f"Missing GrammaticalGender object: {e}")
            for N in ["S", "P"]:
                for G in [F, M]:
                    logger.debug(f'{uid=} {N=} {G.code=} {language=}')
                    try:
                        l = Label.objects.get(
                            uid=uid,
                            gender=G,
                            grammatical_number=N,
                            language=language
                        )
                        logger.debug(l)
                        dictionary[uid][N][G.code]=l.label
                    except Label.DoesNotExist:
                        continue
        return Response(dictionary)