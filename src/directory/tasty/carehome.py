from tastypie import fields
import logging
import json
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle

from django.urls import re_path
from directory.models import (
    Effector,
    CareHome,
)
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)
from directory.utils import (
    get_directory,
    get_effector_nodes,
)

logger=logging.getLogger(__name__)

# We need a generic object to shove data in/get data from.
# Riak generally just tosses around dictionaries, so we'll lightly
# wrap that.

class Obj(object):
    def __init__ (
            self,
            uid,
            regular_permanent_bed,
            regular_temporary_bed,
            alzheimer_permanent_bed,
            alzheimer_temporary_bed,
            uvpha_permanent_bed,
            uhr_permanent_bed,
            day_care
        ):
        self.uid = uid
        self.regular_permanent_bed=regular_permanent_bed
        self.regular_temporary_bed=regular_temporary_bed
        self.alzheimer_permanent_bed=alzheimer_permanent_bed
        self.alzheimer_temporary_bed=alzheimer_temporary_bed
        self.uvpha_permanent_bed=uvpha_permanent_bed
        self.uhr_permanent_bed=uhr_permanent_bed
        self.day_care=day_care

def createResources(request, nodes):
    data= []
    for node in nodes:
        obj = Obj(
            node.uid,
            node.regular_permanent_bed,
            node.regular_temporary_bed,
            node.alzheimer_permanent_bed,
            node.alzheimer_temporary_bed,
            node.uvpha_permanent_bed,
            node.uhr_permanent_bed,
            node.day_care
        )
        #logger.debug(f'{obj=}')
        data.append(obj)
    return data

class CareHomeResource(Resource):
    logger.debug("Hello  CareHomeResource")
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    regular_permanent_bed = fields.IntegerField(
        attribute='regular_permanent_bed',
        null=True
    )
    regular_temporary_bed = fields.IntegerField(
        attribute='regular_temporary_bed',
        null=True
    )
    alzheimer_permanent_bed = fields.IntegerField(
        attribute='alzheimer_permanent_bed',
        null=True
    )
    alzheimer_temporary_bed = fields.IntegerField(
        attribute='alzheimer_temporary_bed',
        null=True
    )
    uvpha_permanent_bed = fields.IntegerField(
        attribute='uvpha_permanent_bed',
        null=True
    )
    uhr_permanent_bed = fields.IntegerField(
        attribute='uhr_permanent_bed',
        null=True
    )
    day_care = fields.IntegerField(
        attribute='day_care',
        null=True
    )

    class Meta:
        resource_name = 'carehomes'
        allowed_methods=['get'] 
        collection_name = "carehomes"
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
        nodes = get_effector_nodes(directory, label="CareHome")
        objs = createResources(request, nodes)
        return objs

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        try :
            node = CareHome.nodes.get(uid=uid)
            resources = createResources(bundle.request, [node])
            return resources[0]
        except Exception as e : 
            raise Exception(f"Can't find node {uid} {e}")