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
)
from rest_framework import serializers

logger=logging.getLogger(__name__)


class SocialNetworkSerializer(serializers.ModelSerializer):
    get_type_display = serializers.CharField()


    class Meta:
        model = SocialNetwork
        fields = ['type', 'get_type_display', 'handle', 'url']


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