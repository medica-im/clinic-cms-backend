from tastypie import fields
import logging
import json
from django.contrib.sites.shortcuts import get_current_site
from common.utils import timeit
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.fields import ForeignKey
from directory.tasty.communes import createCommuneResources
from directory.serializers import TagSerializer

from django.urls import re_path
from django.core.cache import cache
from directory.models import Commune
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)
from directory.utils import (
    get_phones_neomodel,
    get_directory,
    sync_get_entries,
    get_ttl,
    generate_cache_key,
)
from directory.models.core import sync_set_timestamp
from directory.tasty.types import (
    createEffectorTypeResources,
    flex_effector_type_label
)
from django.core.cache import cache
from django.conf import settings

logger=logging.getLogger(__name__)

TTL: int = 60

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
            effector_type,
            commune,
            department,
            address,
            phones,
            updatedAt,
            facility,
            avatar,
            memberships,
            employers,
            tags,
            active
        ):
        self.label = label
        self.name = name
        self.gender = gender
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.effector_type = effector_type
        self.commune = commune
        self.department = department
        self.address = address
        self.phones = phones
        self.updatedAt = updatedAt
        self.facility = facility
        self.avatar = avatar
        self.memberships = memberships
        self.employers = employers
        self.tags = tags
        self.active = active

def createEntryResource(node):
    entry=node["entry"]
    uid = entry.uid
    effector_node=node["effector"]
    address=node["address"]
    commune_node: Commune = node["commune"]
    commune_obj = createCommuneResources([commune_node])[0]
    commune = commune_obj.__dict__
    department = {
        "code": node["department"].code
    }
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
    type_object = createEffectorTypeResources(node["effector_type"])
    type_object = flex_effector_type_label(effector_node, type_object)
    effector_type=type_object.__dict__
    phones = get_phones_neomodel(entry=entry)
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
        "slug": node["facility"].slug,
        "label": node["facility"].label or node["facility"].name
    }
    avatar=node["avatar"]
    memberships=node["memberships"]
    employers=node["employers"]
    try:
        serializer = TagSerializer(node["tags"], many=True)
        tags = serializer.data
    except Exception as e:
        logger.error(e)
        tags = None
    active=entry.active

    entry = EntryObj(
        label,
        name,
        gender,
        slug,
        uid,
        effector_uid,
        effector_type,
        commune,
        department,
        address,
        phones,
        updatedAt,
        facility,
        avatar,
        memberships,
        employers,
        tags,
        active
    )
    return entry

def createEntryResources(nodes: list, request):
    data= []
    # TODO manage Exception Value: 'NoneType' object is not iterable
    try:
        for node in nodes:
            data.append(createEntryResource(node))
    except (TypeError, ValueError) as e:
        logger.error(e)
        pass
    return data

class EntryResource(Resource):
    uid = fields.CharField(attribute='uid')
    active = fields.BooleanField(attribute='active', null=True)
    effector_uid = fields.CharField(attribute='effector_uid')
    label = fields.CharField(attribute='label')
    name = fields.CharField(attribute='name')
    gender = fields.CharField(attribute='gender', null=True)
    slug = fields.CharField(attribute='slug')
    effector_type = fields.DictField(attribute='effector_type')
    commune = fields.DictField(attribute='commune')
    department = fields.DictField(attribute='department', null=True)
    address = fields.DictField(attribute='address', null=True)
    phones = fields.ListField(attribute='phones', null=True)
    facility = fields.DictField(attribute='facility')
    updatedAt = fields.IntegerField(attribute='updatedAt')
    avatar = fields.DictField(attribute='avatar', null=True)
    memberships = fields.ListField(attribute='memberships', null=True)
    employers = fields.ListField(attribute='employers', null=True)
    tags = fields.ListField(attribute='tags', null=True)

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
        logger.debug(f"{directory=}")
        nodes = sync_get_entries(directory)
        logger.debug(f"{nodes[:1] if nodes else []}")
        contacts = createEntryResources(nodes, request)
        return contacts

    @timeit
    def obj_get_list(self, bundle, **kwargs):
        cache_key = generate_cache_key(self._meta.api_name, self._meta.resource_name, bundle.request)
        cached = cache.get(cache_key)
        if cached:
            logger.warning(f"*** Using cache with key {cache_key} ***")
            return cached
        else:
            logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
            value = self.get_object_list(bundle.request)
            endpoint = "%s:%s" % (self._meta.api_name, self._meta.resource_name)
            timeout = get_ttl(endpoint,bundle.request) or TTL
            logger.debug(f"{timeout=}")
            cache.set(
                cache_key,
                value,
                timeout=timeout
            )
            site=get_current_site(bundle.request)
            sync_set_timestamp(endpoint, site)
            return value        

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        directory=get_directory(bundle.request)
        try :
            nodes = sync_get_entries(directory, uid=uid)
            entry = createEntryResources(nodes, bundle.request)
            return entry[0]
        except Exception as e : 
            raise Exception(f"Can't find Entry {uid} {e}")