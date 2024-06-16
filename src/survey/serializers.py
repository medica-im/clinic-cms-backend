import logging
from survey.models import (
    Survey,
    Response,
)
from rest_framework import serializers

logger=logging.getLogger(__name__)


class ResponseSerializer(serializers.ModelSerializer):
    get_moderation_display = serializers.ReadOnlyField()
    created = serializers.ReadOnlyField()


    class Meta:
        model = Response
        fields = [
            'id',
            'survey',
            'created',
            'content',
            'moderation',
            'get_moderation_display'
        ]


class SurveySerializer(serializers.ModelSerializer):
    class Meta:
        model = Survey
        fields = [
            'id',
            'name',
            'label',
            'presentation',
            'is_active',
            'start',
            'end',
            'created',
        ]