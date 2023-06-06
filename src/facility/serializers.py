from facility.models import Organization, Category, Facility
from addressbook.serializers import ContactSerializer
from rest_framework import serializers


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