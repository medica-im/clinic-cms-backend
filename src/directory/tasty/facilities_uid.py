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
from directory.models import Facility
from django.urls import re_path
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)
from django.conf import settings
from facilities import createFacilityResources, FacilityObj

logger=logging.getLogger(__name__)

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
    effectors = fields.ListField(attribute='effectors')


    class Meta:
        resource_name = 'facilities-uid'
        allowed_methods=['get']
        collection_name = "facilities"
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
                r"^(?P<resource_name>%s)/(?P<slug>[\w\d_.-]+)/$"
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
        slug= kwargs['slug']
        try :
            facility = Facility.nodes.get(slug=slug)
            objects = createFacilityResources(bundle.request, [facility])
            return objects[0]
        except Exception as e:
            raise Exception(f"{e}\nCan't find Facility {slug}")