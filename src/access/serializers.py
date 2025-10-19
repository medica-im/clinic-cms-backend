from rest_framework import exceptions, serializers
from access.models import Role
from adrf.serializers import ModelSerializer as AsyncModelSerializer

class RoleSerializer(serializers.ModelSerializer):
    """Serialize Role."""


    class Meta:
        model = Role
        fields = [
            'name',
            'label',
            'description',
        ]


class AsyncRoleSerializer(AsyncModelSerializer):
    """Serialize Role."""

    class Meta:
        model = Role
        fields = [
            'name',
            'label',
            'description',
        ]