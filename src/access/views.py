from rest_framework import viewsets
from .models import AccessControl
from .serializers import AccessControlSerializer

class AccessControlViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = AccessControl.objects.all()
    serializer_class = AccessControlSerializer