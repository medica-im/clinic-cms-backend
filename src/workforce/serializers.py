import logging
from workforce import models
from rest_framework import serializers

logger = logging.getLogger(__name__)

class WorkforceOccupationSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    slug = serializers.SerializerMethodField()


    class Meta:
        model = models.NetworkNode
        fields = (
            'name',
            'slug',
        )
        depth=1
        
    def get_name(self, obj):
        return obj.name
    
    def get_slug(self, obj):
        try:
            logger.debug(f"{obj.slug}")
            return obj.slug.slug
        except models.WorkforceSlug.DoesNotExist:
                return


class RPPSSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.RPPS
        fields = (
            'identifier',
        )
        depth=1


class ADELISerializer(serializers.ModelSerializer):

    class Meta:
        model = models.ADELI
        fields = (
            'identifier',
        )
        depth=1


class ConventionSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Convention
        fields = (
            'name',
            'label',
            'definition',
        )


class PaymentMethodSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.PaymentMethod
        fields = (
            'name',
            'label',
            'definition',
        )


class ThirdPartyPayerSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.ThirdPartyPayer
        fields = (
            'name',
            'label',
            'definition',
        )
