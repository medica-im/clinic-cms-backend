from rest_framework import exceptions, serializers
from access.models import Role, AccessControl, Endpoint


class EndpointSerializer(serializers.ModelSerializer):

    class Meta:
        model = Endpoint
        fields = ['name']


class RoleSerializer(serializers.ModelSerializer):
    """Serialize Role."""

    class Meta:
        model = Role
        fields = [
            'id',
            'name',
            'label',
            'description',
        ]


class AccessControlSerializer(serializers.ModelSerializer):
    role = RoleSerializer()
    endpoint = EndpointSerializer()

    class Meta:
        model = AccessControl
        fields = ['endpoint', 'role', 'permissions']