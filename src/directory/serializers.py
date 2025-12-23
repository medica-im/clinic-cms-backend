from directory.models import Directory, InputField, Setting, Timestamp
from rest_framework import serializers
import langcodes
from adrf.serializers import Serializer
from langcodes import Language
from django.utils.translation import get_language
from django.conf import settings
import logging

logger=logging.getLogger(__name__)

def display_tag_name(tag: str, language: str = settings.LANGUAGE_CODE)->str|None:
        try:
            display_name = Language.get(tag).display_name(language)
            if tag == "arb" and language == "fr":
                display_name = "arabe standard moderne"
            elif tag == "cmn" and language == "fr":
                display_name = "mandarin"
            return display_name
        except:
            return


class TagSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        effector_types=None
        category=None
        try:
            category = instance.tag_category.all()[0]
            try:
                effector_types=[_type.uid for _type in category.effector_type.all()]
            except Exception as e:
                    logger.error(e)
        except Exception as e:
            logger.error(e)
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "category": {
                "name": category.name,
                "label": category.label,
                "labelShort": category.labelShort,
            },
            "effector_types": effector_types
        }


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


class TimestampSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Timestamp
        fields = [
            'endpoint',
            'timestamp',
        ]


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


class SettingSerializer(serializers.ModelSerializer):
    sort_category_display = serializers.CharField(
        source='get_sort_category_display'
    )
    class Meta:
        model = Setting
        fields = [
            'sort_category_display'
        ]


class DirectorySerializer(serializers.ModelSerializer):
    inputField = InputFieldSerializer(
        many=False,
        read_only=True,
        source="inputfield"
    )
    setting = SettingSerializer(
        many=False,
        read_only=True,
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
            'setting',
        ]
        depth = 3


class EffectorSerializer(serializers.Serializer):
    name_fr = serializers.CharField(max_length=255)
    label_fr = serializers.CharField(max_length=255)