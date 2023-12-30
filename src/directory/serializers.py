from directory.models import Directory
from rest_framework import serializers
import logging

logger=logging.getLogger(__name__)

class DirectorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Directory
        fields = [
            'name',
            'display_name',
            'presentation',
            'slug',
            'postal_codes',
        ]


class EffectorSerializer(serializers.Serializer):
    name_fr = serializers.CharField(max_length=255)
    label_fr = serializers.CharField(max_length=255)