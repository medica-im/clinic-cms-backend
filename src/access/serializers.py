from rest_framework import exceptions, serializers
from access.models import Role
from adrf.serializers import ModelSerializer as AsyncModelSerializer

class RoleSerializer(serializers.ModelSerializer):
    """Serialize Role."""


    class Meta:
        model = Role
        # No 'label': role display text lives in the frontend
        # (messages/*.json, src/lib/roles.ts). The field was dropped from the
        # model in access/0005.
        fields = [
            'name',
            'description',
        ]


class AsyncRoleSerializer(AsyncModelSerializer):
    """Serialize Role."""

    class Meta:
        model = Role
        fields = [
            'id',
            'name',
            'description',
        ]