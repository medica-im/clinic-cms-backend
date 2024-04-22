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
    Appointment,
    Address,
)
from rest_framework import serializers

logger=logging.getLogger(__name__)


class SocialNetworkSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )

    class Meta:
        model = SocialNetwork
        fields = ['type', 'type_display', 'handle', 'url']


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
        ]
        depth = 2


class EmailSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )
    class Meta:
        model = Email
        fields = [
            'id',
            'email',
            'type',
            'type_display',
        ]
        depth = 2


class WebsiteSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )
    class Meta:
        model = Website
        fields = [
            'id',
            'website',
            'type',
            'type_display',
        ]
        depth = 2


class AppointmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Appointment
        fields = [
            'url',
            'phone',
            'house_call',
        ]
        depth = 1


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