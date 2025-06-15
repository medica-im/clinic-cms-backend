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
            effectors,
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
        self.effectors = effectors

def createFacilityResources(request, nodes):
    data= []
    for node in nodes:
        facility = node["facility"]
        commune = node["commune"]
        country = node["country"]
        uid = facility.uid
        name = facility.name
        if not name:
            try:
                org=facility.organization.all()[0]
                name = getattr(
                    org,
                    f'name_{settings.LANGUAGE_CODE}',
                    getattr(
                        org,
                        'label_en',
                        None
                    )
                )
            except:
                name=facility.uid
        try:
            label = facility.label
        except:
            label = name
        slug = facility.slug
        try:
            commune_uid = commune.uid
        except Exception as e:
            logger.error(e)
            commune_uid = None
        address = get_address(facility,commune,country)
        organizations = [org.uid for org in facility.organization.all()]
        phones = get_phones_neomodel(f=facility)
        emails = get_emails_neomodel(f=facility)
        websites = get_websites_neomodel(f=facility)
        socialnetworks=get_socialnetworks_neomodel(f=facility)
        avatar = get_avatar_url(f=facility)
        effectors=[e.uid for e in facility.effectors.all()]
        obj = FacilityObj(
            uid,
            name,
            label,
            slug,
            commune_uid,
            address,
            organizations,
            phones,
            emails,
            websites,
            socialnetworks,
            avatar,
            effectors,
        )
        data.append(obj)
    return data

class FacilityResource(Resource):
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
        resource_name = 'facilities'
        allowed_methods=['get']
        collection_name = "facilities"
        authorization = Authorization()
        detail_uri_name = 'slug'

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}

        if isinstance(bundle_or_obj, Bundle):
            kwargs['slug'] = bundle_or_obj.obj.slug
        else:
            kwargs['slug'] = bundle_or_obj.slug
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