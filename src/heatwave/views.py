import logging
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from heatwave.utils import get_heatwave_by_department

logger = logging.getLogger(__name__)

@api_view()
def heatwave_department(request, pk):
    logger.debug(f"heatwave view, {pk=}")
    try:
        res_dct = get_heatwave_by_department(pk)
    except Exception as e:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(res_dct)
