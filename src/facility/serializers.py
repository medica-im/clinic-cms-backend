from facility.models import Organization, Category, Facility, LegalEntity
from addressbook.api.serializers import ContactSerializer
from rest_framework import serializers


class LegalEntitySerializer(serializers.ModelSerializer):

    class Meta:
        model= LegalEntity
        fields= [
            'id',
            'name',
            'type',
            'get_type_display',
            'RNA',
            'SIREN',
            'SIRET',
            'RCS',
            'SHARE_CAPITAL',
            'VAT',
        ]


class FacilitySerializer(serializers.ModelSerializer):
    contact = ContactSerializer(many=False, read_only=True)
    
    class Meta:
        model = Facility
        fields = [
            'id',
            'name',
            'contact',
        ]
        depth = 3


class OrganizationSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(many=False, read_only=True)
    facility = FacilitySerializer(many=True, read_only=True)
    legal_entity = LegalEntitySerializer(many=False, read_only=True)

    class Meta:
        model = Organization
        fields = [
            'id',
            'name',
            'company_name',
            'language',
            'formatted_name',
            'formatted_name_definite_article',
            'website_title',
            'website_description',
            'category',
            'contact',
            'facility',
            'registration',
            'google_site_verification',
            'city',
            'legal_entity'
        ]
        depth = 4


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'formatted_name',
            'definition',
            'slug',
        ]