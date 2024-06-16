import logging

from survey.models import Response, Survey
from survey.serializers import SurveySerializer, ResponseSerializer
from survey.permissions import ResponsePermissions
from access.utils import get_role
from rest_framework import generics, status, viewsets
from django.http import Http404

logger = logging.getLogger(__name__)

class ResponseViewSet(viewsets.ModelViewSet):
    serializer_class = ResponseSerializer
    permission_classes = [ResponsePermissions]

    def get_queryset(self, survey=None):
        survey = self.kwargs.get('survey')
        logger.debug(f'{survey=}')
        role = get_role(self.request)
        logger.debug(f'{role=}')
        logger.debug(f'{role.name=}')
        try:
            survey = Survey.objects.get(name=survey)
            logger.debug(f"{survey=}")
        except Survey.DoesNotExist:
            return
        if role.name == "anonymous":
            qs = Response.objects.filter(
                survey=survey,
                moderation='PU'
            )
            logger.debug(f'{qs.count()=} {qs=}')
            return qs
        else:
            qs = Response.objects.filter(
                survey=survey,
            )
            logger.debug(f'{qs.count()=} {qs=}')
            return qs

    """
    def create(self, request):
        changed_by = self.request.user
        organization = get_organization(self.request)
        roles = self.request.data.get("roles", None)
        text = self.request.data.get("text", None)
        if roles:
            serializer.save(
                changed_by=changed_by,
                text=text,
                roles=roles,
                organization=organization
            )
        else:
            serializer.save(
                changed_by=changed_by,
                text=text,
                organization=organization
            )
        return
        """
    
class SurveyViewSet(viewsets.ModelViewSet):
    queryset = Survey.objects.all()
    serializer_class = SurveySerializer
    lookup_field = 'name'
    #permission_classes = []

    """
    def get_queryset(self):
        name = self.request.GET.get('name')
        logger.debug(name);
        try:
            survey = Survey.objects.get(name=name)
            logger.debug(f"{survey=}")
            return survey
        except:
            return
    """

    def create(self, request):
        """
        changed_by = self.request.user
        organization = get_organization(self.request)
        roles = self.request.data.get("roles", None)
        text = self.request.data.get("text", None)
        if roles:
            serializer.save(
                changed_by=changed_by,
                text=text,
                roles=roles,
                organization=organization
            )
        else:
            serializer.save(
                changed_by=changed_by,
                text=text,
                organization=organization
            )
        """
        return