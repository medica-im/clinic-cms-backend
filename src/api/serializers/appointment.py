from rest_framework import serializers


class AppointmentSerializer(serializers.Serializer):
    """Validates appointment data read from the graph; writes go through
    api.asyncserializers.appointment."""
    uid = serializers.CharField(required=False)
    entry = serializers.CharField(required=False)
    url = serializers.URLField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True)
    location = serializers.ChoiceField(choices=['office', 'house_call'], allow_null=True)
