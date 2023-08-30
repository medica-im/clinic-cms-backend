from addressbook.models import Contact, Address, SocialNetwork, PhoneNumber
from rest_framework import serializers, fields

class SocialNetworkSerializer(serializers.ModelSerializer):
    #name = serializers.SerializerMethodField()
    #name = serializers.CharField(source='get_type_display')

    class Meta:
        model = SocialNetwork
        fields = [
            'type',
            'get_type_display',
            'handle',
            'url',
            'public_visible',
            'contact_visible',
        ]
        
        depth = 2


class PhoneNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhoneNumber
        fields = [
            'id',
            'phone',
            'type',
            'get_type_display',
        ]
        depth = 2


class AddressSerializer(serializers.ModelSerializer):
    facility_uid = serializers.SerializerMethodField()

    class Meta:
        model = Address
        fields = [
            'id',
            'facility_uid',
            'building',
            'street',
            'geographical_complement',
            'city',
            'zip',
            'state',
            'country',
            'latitude',
            'longitude',
            'zoom',
        ]
        depth = 2

    def get_facility_uid(self, obj):
        return obj.contact.neomodel_uid


class ContactSerializer(serializers.ModelSerializer):
    socialnetworks = SocialNetworkSerializer(read_only=True, many=True)

    class Meta:
        model = Contact
        fields = [
            'id',
            'formatted_name',
            'formatted_name_definite_article',
            'url',
            'address',
            'phonenumbers',
            'socialnetworks',
            'websites',
        ]
        depth = 3