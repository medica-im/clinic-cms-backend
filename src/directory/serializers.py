from directory.models import Directory, InputField
from rest_framework import serializers
from langcodes import Language
from django.utils.translation import get_language
import logging

logger=logging.getLogger(__name__)



def display_tag_name(tag: [str])->[str]:
        try:
            Language.make(language=tag).display_name(get_language())
        except:
            return

class SpokenLanguageSerializer(serializers.Serializer):
    display_name = serializers.CharField()

    def create(self, validated_data):
        return

    def update(self, instance, validated_data):
        display_name_data = validated_data.get(
            'display_name',
            instance.display_name
        )
        instance.display_name = display_tag_name(display_name_data)
        instance.save()
        return instance


class ThirdPartyPayerSerializer(serializers.Serializer):
    uid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(
        required=True,
        allow_blank=False,
    )
    label_fr = serializers.CharField(
        required=True,
        allow_blank=False,
    )
    label_en = serializers.CharField(
        required=True,
        allow_blank=False,
    )
    definition_fr = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    definition_en = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def create(self, validated_data):
        return

    def update(self, instance, validated_data):
        instance.uid = validated_data.get('uid', instance.uid)
        instance.name = validated_data.get('name', instance.name)
        instance.label = validated_data.get('label', instance.label)
        instance.label_en = validated_data.get('label_en', instance.label_en)
        instance.definition_fr = validated_data.get(
            'definition_fr',
            instance.definition_fr
        )
        instance.definition_en = validated_data.get(
            'definition_en',
            instance.definition_en
        )
        instance.save()
        return instance


class ConventionSerializer(serializers.Serializer):
    uid = serializers.UUIDField(read_only=True)
    name = serializers.CharField(
        required=True,
        allow_blank=False,
    )
    label = serializers.CharField(
        required=True,
        allow_blank=False,
    )
    definition = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def create(self, validated_data):
        return

    def update(self, instance, validated_data):
        instance.uid = validated_data.get('uid', instance.uid)
        instance.name = validated_data.get('name', instance.name)
        instance.label = validated_data.get('label', instance.label)
        instance.definition = validated_data.get(
            'definition',
            instance.definition
        )
        instance.save()
        return instance


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