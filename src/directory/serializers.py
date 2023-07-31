from rest_framework import serializers

class EffectorSerializer(serializers.Serializer):
    name_fr = serializers.CharField(max_length=255)
    label_fr = serializers.CharField(max_length=255)