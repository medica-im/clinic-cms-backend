from addressbook.models import Contact, Address, SocialNetwork, PhoneNumber
from rest_framework import serializers, fields

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


