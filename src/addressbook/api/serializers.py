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
)
from access.serializers import AsyncRoleSerializer
from rest_framework import serializers
from adrf.serializers import Serializer, ModelSerializer as AsyncModelSerializer

logger=logging.getLogger(__name__)


class AsyncSocialNetworkSerializer(AsyncModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )

    # Names, not nested objects — see AsyncPhoneNumberModelSerializer. Without
    # this the `depth` below expands each Role into {"id", "name",
    # "description"}, which api.types.socialmedia.SocialMedia rejects: the row
    # is written, the response fails to validate, and the client sees a 500 on
    # a request that actually succeeded.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )

    class Meta:
        model = SocialNetwork
        fields = [
            'id',
            'type',
            'type_display',
            'url',
            'roles',
        ]
        depth = 2


class SocialNetworkSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display'
    )

    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
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


class AsyncProfileSerializer(AsyncModelSerializer):
    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )

    class Meta:
        model = Profile
        fields = [
            'id', 'contact', 'roles', 'organization', 'text', 'changed_by',
            'created', 'updated',
        ]
        extra_kwargs = {'changed_by': {'required': False}}


class ProfileSerializer(serializers.ModelSerializer):
    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
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
    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
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
    # Names, not nested objects. A role's id and description are not
    # something any client can use — the frontend renders the label from
    # src/lib/roles.ts and authorises nothing itself — and shipping them
    # under every phone, email and website of every entry meant a field
    # nobody read could still 500 the response that carried it.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
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
    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
    class Meta:
        model = Email
        fields = [
            'id',
            'email',
            'roles',
        ]
        depth = 2


class AsyncEmailSerializer(AsyncModelSerializer):
    # Names, not nested objects. A role's id and description are not
    # something any client can use — the frontend renders the label from
    # src/lib/roles.ts and authorises nothing itself — and shipping them
    # under every phone, email and website of every entry meant a field
    # nobody read could still 500 the response that carried it.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
    class Meta:
        model = Email
        fields = [
            'id',
            'email',
            'roles',
        ]
        depth = 2


class WebsiteSerializer(serializers.ModelSerializer):

    # Names, not nested objects — see AsyncPhoneNumberModelSerializer.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
    class Meta:
        model = Website
        fields = [
            'id',
            'url',
            'roles',
        ]
        depth = 2


class AsyncWebsiteSerializer(AsyncModelSerializer):
    # Names, not nested objects. A role's id and description are not
    # something any client can use — the frontend renders the label from
    # src/lib/roles.ts and authorises nothing itself — and shipping them
    # under every phone, email and website of every entry meant a field
    # nobody read could still 500 the response that carried it.
    roles = serializers.SlugRelatedField(
        slug_field='name', read_only=True, many=True
    )
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

    # No `address` field. A facility's address lives on the Facility node —
    # street, zip, building, geographical_complement, location — and the
    # organisation payload reads it there, through the same Entry → Facility
    # walk it already performs for commune and department. The method that
    # used to sit here did that walk too, reached by way of a Contact row that
    # supplied only the neomodel_uid; OrganizationSerializer was its one caller
    # and now overwrites the key, so keeping it would mean two answers to the
    # same question with nothing keeping them in step.

    class Meta:
        model = Contact
        fields = [
            'id',
            'formatted_name',
            'formatted_name_definite_article',
            'url',
            'phonenumbers',
            'socialnetworks',
            'websites',
            'emails',
        ]
        depth = 3
