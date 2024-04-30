from tastypie import fields
import logging
import json
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
    get_phones_neomodel,
    get_directory,
    get_entries
)
from directory.tasty.types import (
    createEffectorTypeResources,
    flex_effector_type_label
)
from django.core.cache import cache
from django.conf import settings

logger=logging.getLogger(__name__)

# We need a generic object to shove data in/get data from.
# Riak generally just tosses around dictionaries, so we'll lightly
# wrap that.

class EntryObj(object):
    def __init__ (
            self,
            label,
            name,
            gender,
            slug,
            uid,
            effector_uid,
            types,
            commune,
            address,
            phones,
            updatedAt,
            facility,
            avatar,
        ):
        self.label = label
        self.name = name
        self.gender = gender
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.types = types
        self.commune = commune
        self.address = address
        self.phones = phones
        self.updatedAt = updatedAt
        self.facility = facility
        self.avatar = avatar

def createEntryResource(request, node):
    entry=node["entry"]
    uid = entry.uid
    effector_node=node["effector"]
    address=node["address"]
    commune_node: Commune = node["commune"]
    commune_obj = createCommuneResources(
        request,
        [commune_node]
    )[0]
    commune = commune_obj.__dict__
    logger.debug(commune)
    label = getattr(
        effector_node,
        f'label_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'label_en',
            None
        )
    )
    name = getattr(
        effector_node,
        f'name_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'name_en',
            None
        )
    )
    gender = effector_node.gender
    slug = getattr(
        effector_node,
        f'slug_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'slug_en',
            None
        )
    )
    effector_uid = effector_node.uid
    type_objects = createEffectorTypeResources(request, node["types"])
    type_objects = [
        flex_effector_type_label(effector_node, type_object, request)
        for type_object in type_objects
    ]
    types=[t.__dict__ for t in type_objects]
    phones = get_phones_neomodel(
        e=effector_node,
        ef=node["location"],
        f=node["facility"],
    )
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
            entry.contactUpdatedAt,
        ]
    )
    facility = {
        "uid": node["facility"].uid,
        "name": node["facility"].name,
        "slug": node["facility"].slug
    }
    avatar=node["avatar"]

    entry = EntryObj(
        label,
        name,
        gender,
        slug,
        uid,
        effector_uid,
        types,
        commune,
        address,
        phones,
        updatedAt,
        facility,
        avatar,
    )
    logger.debug(f'{entry=}')
    return entry

def createEntryResources(request, nodes):
    data= []
    # TODO manage Exception Value: 'NoneType' object is not iterable
    try:
        for node in nodes:
            data.append(createEntryResource(request, node))
    except TypeError:
        pass
    return data

class EntryResource(Resource):
    uid = fields.CharField(attribute='uid')
    effector_uid = fields.CharField(attribute='effector_uid')
    label = fields.CharField(attribute='label')
    name = fields.CharField(attribute='name')
    gender = fields.CharField(attribute='gender', null=True)
    slug = fields.CharField(attribute='slug')
    types = fields.ListField(attribute='types')
    commune = fields.DictField(attribute='commune')
    address = fields.DictField(attribute='address', null=True)
    phones = fields.ListField(attribute='phones', null=True)
    facility = fields.DictField(attribute='facility')
    updatedAt = fields.IntegerField(attribute='updatedAt')
    avatar = fields.DictField(attribute='avatar', null=True)

    class Meta:
        resource_name = 'entries'
        allowed_methods=['get'] 
        collection_name = "entries"
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
        nodes = get_entries(directory)
        contacts = createEntryResources(request, nodes)
        return contacts

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        directory=get_directory(bundle.request)
        logger.debug(f'{directory=}')
        try :
            nodes = get_entries(directory, uid)
            entry = createEntryResources(bundle.request, nodes)
            return entry[0]
        except Exception as e : 
            raise Exception(f"Can't find Entry {uid} {e}")