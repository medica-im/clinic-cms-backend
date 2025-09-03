import logging
from addressbook.models import (
    Contact,
    Profile,
    App,
    AppLink,
    AppStore,
    SocialNetwork,
    PhoneNumber,
    Email,
    Website,
    Address,
)
from directory.models.graph import Appointment, Office, HouseCall, Entry
from rest_framework import serializers

logger=logging.getLogger(__name__)


class SocialNetworkSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )

    class Meta:
        model = SocialNetwork
        fields = [
            'type',
            'type_display',
            'handle',
            'url',
            'roles',
        ]
        depth = 2


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'id', 'contact', 'roles', 'organization', 'text', 'changed_by',
            'created', 'updated',
        ]
        extra_kwargs = {'changed_by': {'required': False}}


class AppStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppStore
        fields = [
            'name', 'image',
        ]


class AppLinkSerializer(serializers.ModelSerializer):
    store = AppStoreSerializer(read_only=True, many=False)

    class Meta:
        model = AppLink
        fields = [
            'url', 'store',
        ]


class AppSerializer(serializers.ModelSerializer):
    links = AppLinkSerializer(read_only=True, many=True)

    class Meta:
        model = App
        fields = [
            'name', 'label', 'links',
        ]
        
class PhoneNumberSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )
    class Meta:
        model = PhoneNumber
        fields = [
            'id',
            'phone',
            'type',
            'type_display',
            'roles',
            'contact',
        ]
        depth = 2


class EmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Email
        fields = [
            'id',
            'email',
            'roles',
        ]
        depth = 2


class WebsiteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Website
        fields = [
            'id',
            'url',
            'roles',
        ]
        depth = 2


class AppointmentSerializer(serializers.Serializer):
    entry = serializers.CharField()
    url = serializers.URLField(required=False)
    phone = serializers.CharField(required=False)
    location = serializers.ChoiceField(choices=['office', 'house_call', None])

    def create(self, validated_data):
        if validated_data.location is None:
            a = Appointment(url=validated_data.url,phone=validated_data.phone)
        elif validated_data.location == 'office':
            a = Office(url=validated_data.url,phone=validated_data.phone)
        elif validated_data.location == 'house_call':
            a = HouseCall(url=validated_data.url,phone=validated_data.phone)
        try:
            entry = Entry.nodes.get(uid=validated_data.entry)
        except Exception as e:
            logger.error(e)
            raise serializers.ValidationError(f"Entry {validated_data.entry} not found")
        entry.appointments.connect(a)
        return a


class ContactSerializer(serializers.ModelSerializer):
    socialnetworks = SocialNetworkSerializer(read_only=True, many=True)
    emails = EmailSerializer(read_only=True, many=True)

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
            'emails',
        ]
        depth = 3


class AddressSerializer(serializers.ModelSerializer):
    facility_uid = serializers.SerializerMethodField()
    tooltip_direction = serializers.CharField(
        source='get_tooltip_direction_display'
    )

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
            'tooltip_direction',
            'tooltip_permanent',
            'tooltip_text',
        ]
        depth = 2

    def get_facility_uid(self, obj):
        return obj.contact.neomodel_uid