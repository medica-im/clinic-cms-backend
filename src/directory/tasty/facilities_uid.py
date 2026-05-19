'''
Created on Nov 5, 2023

@author: elkcloner
'''
from tastypie import fields
import logging
from directory.utils import (
    get_facilities,
    get_directory,
    get_address,
    get_phones_neomodel,
    get_emails_neomodel,
    get_socialnetworks_neomodel,
    get_websites_neomodel,
    get_avatar_url
)
from directory.models import Facility, Commune, Country
from django.urls import re_path
from tastypie.authorization import Authorization
from tastypie.exceptions import NotFound
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)
from directory.tasty.facilities import createFacilityResources
from django.conf import settings

logger=logging.getLogger(__name__)

class FacilityObj(object):
    def __init__ (
            self,
            uid,
            name,
            label,
            slug,
            commune,
            address,
            organizations,
            phones,
            emails,
            websites,
            socialnetworks,
            avatar,
            entries,
            ban_id,
            ban_banId,
        ):
        self.uid = uid
        self.name = name
        self.label = label
        self.slug = slug
        self.commune = commune
        self.address = address
        self.organizations = organizations
        self.phones = phones
        self.emails = emails
        self.websites = websites
        self.socialnetworks = socialnetworks
        self.avatar = avatar
        self.entries = entries
        self.ban_id = ban_id
        self.ban_banId = ban_banId

class FacilityUidResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    name = fields.CharField(attribute='name', null=True)
    label = fields.CharField(attribute='label', null=True)
    slug = fields.CharField(attribute='slug', null=True)
    commune = fields.CharField(attribute='commune', null=True)
    address = fields.DictField(attribute='address', null=True)
    organizations = fields.ListField(attribute='organizations', null=True)
    phones = fields.ListField(attribute='phones', null=True)
    emails = fields.ListField(attribute='emails', null=True)
    websites = fields.ListField(attribute='websites', null=True)
    socialnetworks = fields.ListField(attribute='socialnetworks', null=True)
    avatar = fields.DictField(attribute='avatar', null=True)
    entries = fields.ListField(attribute='entries', null=True)
    ban_id = fields.CharField(attribute='ban_id', null=True)
    ban_banId = fields.CharField(attribute='ban_banId', null=True)

    class Meta:
        resource_name = 'facilitiesuid'
        allowed_methods=['get']
        collection_name = "facilitiesuid"
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
        nodes = get_facilities(directory=directory)
        objects = createFacilityResources(request, nodes)
        return objects

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        directory=get_directory(bundle.request)
        uid = kwargs['uid']
        logger.debug(f"{directory=}")
        logger.debug(f"{uid=}")
        try:
            facilities = get_facilities(directory=directory, uid=uid)
            logger.debug(f"{facilities}")
            objects = createFacilityResources(bundle.request, facilities)
            return objects[0]
        except IndexError:
            raise NotFound(f"Can't find Facility {uid}")