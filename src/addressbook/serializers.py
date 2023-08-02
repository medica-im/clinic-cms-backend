from addressbook.models import Contact, Address, SocialNetwork
from rest_framework import serializers, fields

"""
class ChoiceField(serializers.ChoiceField):

    def to_representation(self, obj):
        if obj == '' and self.allow_blank:
            return obj
        return self._choices[obj]

    def to_internal_value(self, data):
        # To support inserts with the value
        if data == '' and self.allow_blank:
            return ''

        for key, val in self._choices.items():
            if val == data:
                return key
        self.fail('invalid_choice', input=data)
"""

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


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id',
            'street',
            'city',
            'zip',
            'state',
            'country',
            'latitude',
            'longitude',
            'zoom',
        ]
        depth = 2


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