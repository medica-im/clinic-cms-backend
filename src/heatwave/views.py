import logging
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from heatwave.utils import get_heatwave_by_department, get_heatwave_by_department_carte
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

class Heatwave(APIView):
    def get(self, request, pk, format=None):
        logger.debug(f"heatwave view, {pk=}")
        try:
            res_dct = get_heatwave_by_department_carte(pk)
        except Exception as e:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(res_dct)
