from directory.models import Directory, InputField
from rest_framework import serializers
import logging

logger=logging.getLogger(__name__)

class InputFieldSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = InputField
        fields = [
            'geocoder',
            'situation',
            'commune',
            'category',
            'facility',
            'search',
        ]


class DirectorySerializer(serializers.ModelSerializer):
    inputField = InputFieldSerializer(
        many=False,
        read_only=True,
        source="inputfield"
    )

    class Meta:
        model = Directory
        fields = [
            'name',
            'display_name',
            'presentation',
            'slug',
            'postal_codes',
            'inputField',
        ]
        depth = 3


class EffectorSerializer(serializers.Serializer):
    name_fr = serializers.CharField(max_length=255)
    label_fr = serializers.CharField(max_length=255)