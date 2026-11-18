from rest_framework import serializers
from .models import GrammaticalGender
import logging

logger = logging.getLogger(__name__)

class GrammaticalGenderSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = GrammaticalGender
        fields = (
            'name',
            'label',
            'code',
        )