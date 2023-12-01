from tastypie import fields
import logging
import json
from directory.utils import directory_effectors, get_directory
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.fields import ForeignKey
from directory.tasty.communes import createCommuneResources

from django.urls import re_path
from directory.models import Effector, Situation, EffectorType, Commune
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)
from directory.utils import (
    get_phones,
    get_effectors,
)
from directory.tasty.communes import CommuneResource
from directory.tasty.types import createEffectorTypeResources

from django.conf import settings

logger=logging.getLogger(__name__)

# We need a generic object to shove data in/get data from.
# Riak generally just tosses around dictionaries, so we'll lightly
# wrap that.

class EffectorObj(object):
    def __init__ (
            self,
            label,
            name,
            slug,
            uid,
            effector_uid,
            types,
            commune,
            address,
            phones,
        ):
        self.label = label
        self.name = name
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.types = types
        self.commune = commune
        self.address = address
        self.phones = phones


def createEffectorRessources(request, nodes):
    data= []
    for node in nodes:
        effector=node["effector"]
        location=node["location"]
        address=node["address"]
        commune_node: Commune = node["commune"]
        commune_obj = createCommuneResources(
            request,
            [commune_node]
        )[0]
        commune = commune_obj.__dict__
        logger.debug(commune)
        label = getattr(
            effector,
            f'label_{settings.LANGUAGE_CODE}',
            getattr(
                effector,
                'label_en',
                None
            )
        )
        name = getattr(
            effector,
            f'name_{settings.LANGUAGE_CODE}',
            getattr(
                effector,
                'name_en',
                None
            )
        )
        slug = getattr(
            effector,
            f'slug_{settings.LANGUAGE_CODE}',
            getattr(
                effector,
                'slug_en',
                None
            )
        )
        uid = location.uid
        effector_uid = effector.uid
        types_obj = createEffectorTypeResources(request, node["types"])
        types=[t.__dict__ for t in types_obj]
        phones = get_phones(request, effector)
        effector = EffectorObj(
            label,
            name,
            slug,
            uid,
            effector_uid,
            types,
            commune,
            address,
            phones
        )
        logger.debug(f'{effector=}')
        data.append(effector)
    return data

class EffectorResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    effector_uid = fields.CharField(attribute='effector_uid')
    label = fields.CharField(attribute='label')
    name = fields.CharField(attribute='name')
    slug = fields.CharField(attribute='slug')
    types = fields.ListField(attribute='types')
    commune = fields.DictField(attribute='commune')
    address = fields.DictField(attribute='address')
    phones = fields.ListField(attribute='phones')

    class Meta:
        resource_name = 'effectors'
        allowed_methods=['get'] 
        collection_name = "effectors"
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
        #effectorNodes = Effector.nodes.all()
        effectorNodes = directory_effectors(directory)
        effectors = createEffectorRessources(request, effectorNodes)
        return effectors

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        try :
            effectorNode = Effector.nodes.get(uid=uid)
            effector = createEffectorRessources(bundle.request, [effectorNode])
            return effector[0]
        except Exception as e : 
            raise Exception(f"Can't find Effector {uid} {e}")


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