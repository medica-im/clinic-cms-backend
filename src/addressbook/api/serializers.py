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
from access.serializers import AsyncRoleSerializer
from directory.models.graph import Appointment, Office, HouseCall, Entry
from rest_framework import serializers
from adrf.serializers import Serializer, ModelSerializer as AsyncModelSerializer

logger=logging.getLogger(__name__)


class SocialNetworkSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )

    class Meta:
        model = SocialNetwork
        fields = [
            'id',
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


class AsyncPhoneNumberModelSerializer(AsyncModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )
    roles = AsyncRoleSerializer(read_only=True, many=True)
    class Meta:
        model = PhoneNumber
        fields = [
            'id',
            'phone',
            'type',
            'type_display',
            'roles',
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


class AsyncEmailSerializer(AsyncModelSerializer):
    roles = AsyncRoleSerializer(read_only=True, many=True)
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


class AsyncWebsiteSerializer(AsyncModelSerializer):
    roles = AsyncRoleSerializer(read_only=True, many=True)
    class Meta:
        model = Website
        fields = [
            'id',
            'url',
            'roles',
        ]
        depth = 2


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