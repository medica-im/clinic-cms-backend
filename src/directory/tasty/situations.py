from tastypie import fields
import logging
import json
from directory.utils import get_directory
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle

from django.urls import re_path
from directory.models import Situation
from tastypie.utils import (
    trailing_slash,
)
from directory.utils import (
    get_effectors,
)
from django.conf import settings

logger=logging.getLogger(__name__)

class SituationObj(object):
    def __init__ (
            self,
            uid,
            name,
            effectors,
        ):
        self.uid = uid
        self.name = name
        self.effectors = effectors

def createSituationResources(request, nodes):
    data= []
    for node in nodes:
        uid = node.uid
        name = getattr(
            node,
            f'name_{settings.LANGUAGE_CODE}',
            'name_en'
        )
        effectors = get_effectors(request, node)
        situation = SituationObj(
            uid,
            name,
            effectors,
        )
        data.append(situation)
    return data


class SituationResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    name = fields.CharField(attribute='name')
    effectors = fields.ListField(attribute='effectors')

    class Meta:
        resource_name = 'situations'
        allowed_methods=['get']
        collection_name = "situations"
        authorization = Authorization()
        detail_uri_name = 'uid'

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}

        if isinstance(bundle_or_obj, Bundle):
            kwargs['uid'] = bundle_or_obj.obj.uid
        else:
            kwargs['uid'] = bundle_or_obj.uid
        return kwargs

    def prepend_urls(self):
        return [
            re_path(
                r"^(?P<resource_name>%s)/(?P<uid>[\w\d_.-]+)/$"
                % self._meta.resource_name,
                self.wrap_view('dispatch_detail'),
                name="api_dispatch_detail"),
            re_path(
                r"^(?P<resource_name>%s)/set/(?P<%s_list>.*?)%s$"
                % (
                    self._meta.resource_name,
                    self._meta.detail_uri_name,
                    trailing_slash
                ),
                self.wrap_view('get_multiple'), name="api_get_multiple"),
        ]

    def get_object_list(self, request):
        directory=get_directory(request)
        logger.debug(directory)
        nodes = Situation.nodes.all()
        situations = createSituationResources(request, nodes)
        return situations

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        try :
            node = Situation.nodes.get(uid=uid)
            situation = createSituationResources([node])
            return situation[0]
        except Exception as e:
            raise Exception(f"{e}\nCan't find Situation {uid}")