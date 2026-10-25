import logging
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from opengraph.models import TwitterCard
from opengraph.serializers import (
    TwitterCardSerializer,
)


logger=logging.getLogger(__name__)


class OpenGraphView(RetrieveAPIView):
    queryset = TwitterCard.objects.all()
    serializer_class = TwitterCardSerializer

    def retrieve(self, request, *args, **kwargs):
        card = TwitterCard.objects.filter(site=request.site).first()
        if card is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(card).data)