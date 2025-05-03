'''
Created on Nov 5, 2023

@author: elkcloner
'''
from tastypie import fields
import logging
from directory.utils import directory_effectors, get_directory
from directory.models import Commune
from django.urls import re_path
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.utils import trailing_slash
from django.conf import settings

logger=logging.getLogger(__name__)

class CommuneObj(object):
    def __init__ (
            self,
            uid,
            name,
            slug,
            wikidata,
        ):
        self.uid = uid
        self.name = name
        self.slug = slug
        self.wikidata = wikidata
        
def createCommuneResources(request, nodes):
    data= []
    for node in nodes:
        uid=node.uid
        name = getattr(
            node,
            f'name_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'name_en',
                None
            )
        )
        slug = getattr(
            node,
            f'slug_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'slug_en',
                None
            )
        )
        wikidata = getattr(
            node,
            'wikidata',
        )
        commune = CommuneObj(
            uid,
            name,
            slug,
            wikidata
        )
        data.append(commune)
    return data

class CommuneResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    name = fields.CharField(attribute='name')
    slug = fields.CharField(attribute='slug')
    wikidata = fields.CharField(attribute='wikidata')


    class Meta:
        resource_name = 'commune'
        allowed_methods=['get']
        collection_name = "commune"
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
        nodes = Commune.nodes.all()
        situations = createCommuneResources(request, nodes)
        return situations

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        try :
            node = Commune.nodes.get(uid=uid)
            situation = createCommuneResources([node])
            return situation[0]
        except Exception as e:
            raise Exception(f"{e}\nCan't find Situation {uid}")