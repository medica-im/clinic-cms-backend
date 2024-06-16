from django.urls import path
from survey.views import ResponseViewSet, SurveyViewSet

app_name = 'survey'

from rest_framework import routers

router = routers.SimpleRouter()
router.register(
    r'(?P<survey>[\w-]+)/responses',
    ResponseViewSet,
    basename="responses"
)
router.register(r'', SurveyViewSet, basename="surveys")
urlpatterns = router.urls
