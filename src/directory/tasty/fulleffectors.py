from tastypie import fields
import logging
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
    find_effector_uid,
    find_effector,
)
from directory.tasty.types import createEffectorTypeResources
from django.core.cache import cache
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
            effector_type,
            commune,
            address,
            phones,
            updatedAt,
            facility,
            emails,
            websites,
            socialnetworks,
            appointments,
            profile,
        ):
        self.label = label
        self.name = name
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.effector_type = effector_type
        self.commune = commune
        self.address = address
        self.phones = phones
        self.updatedAt = updatedAt
        self.facility = facility
        self.emails = emails
        self.websites = websites
        self.socialnetworks = socialnetworks
        self.appointments = appointments
        self.profile = profile

def createEffectorRessource(request, node):
    location=node["location"]
    uid = location.uid
    effector_node=node["effector"]
    address=node["address"]
    commune_node: Commune = node["commune"]
    commune_obj = createCommuneResources(
        request,
        [commune_node]
    )[0]
    commune = commune_obj.__dict__
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
    et = node["effector_type"]
    logger.debug(f"{et=}")
    type_obj_lst = createEffectorTypeResources(request, [et])
    logger.debug(f"{type_obj_lst=}")
    type_obj=type_obj_lst[0]
    logger.debug(f"{type_obj=}")
    effector_type=type_obj.__dict__
    logger.debug(f"{effector_type=}")
    phones = get_phones(request, effector_node)
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
            location.contactUpdatedAt,
        ]
    )
    facility = node["facility"].uid
    emails = node["emails"]
    websites = node["websites"]
    socialnetworks = node["socialnetworks"]
    appointments = node["appointments"]
    profile = node["profile"]
    effector = EffectorObj(
        label,
        name,
        slug,
        uid,
        effector_uid,
        effector_type,
        commune,
        address,
        phones,
        updatedAt,
        facility,
        emails,
        websites,
        socialnetworks,
        appointments,
        profile,
    )
    return effector

def createEffectorRessources(request, nodes):
    data= []
    # TODO manage Exception Value: 'NoneType' object is not iterable
    try:
        for node in nodes:
            data.append(createEffectorRessource(request, node))
    except TypeError:
        pass
    return data

class FullEffectorResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    effector_uid = fields.CharField(attribute='effector_uid')
    label = fields.CharField(attribute='label')
    name = fields.CharField(attribute='name')
    slug = fields.CharField(attribute='slug')
    effector_type = fields.DictField(attribute='effector_type')
    commune = fields.DictField(attribute='commune')
    address = fields.DictField(attribute='address', null=True)
    phones = fields.ListField(attribute='phones')
    facility = fields.CharField(attribute='facility')
    updatedAt = fields.IntegerField(attribute='updatedAt')
    emails = fields.ListField(attribute='emails', null=True)
    websites = fields.ListField(attribute='websites', null=True)
    socialnetworks = fields.ListField(attribute='socialnetworks', null=True)
    appointments = fields.ListField(attribute='appointments', null=True)
    profile = fields.DictField(attribute='profile', null=True)


    class Meta:
        resource_name = 'fulleffector'
        allowed_methods=['get'] 
        collection_name = "fulleffectors"
        authorization = Authorization()
        #detail_uri_name = 'uid'
        detail_uri_name = "type"

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}

        #if isinstance(bundle_or_obj, Bundle):
        #    kwargs['type'] = bundle_or_obj.obj.type
        #else:
        #    kwargs['type'] = bundle_or_obj.uid
        return kwargs

    """
    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}

        if isinstance(bundle_or_obj, Bundle):
            kwargs['commune'] = bundle_or_obj.obj.commune
            kwargs['type'] = bundle_or_obj.obj.type
            kwargs['name'] = bundle_or_obj.obj.name

        else:
            kwargs['commune'] = bundle_or_obj.commune
            kwargs['type'] = bundle_or_obj.type
            kwargs['name'] = bundle_or_obj.name
        logger.debug(f'{kwargs.__dict__=}')
        return kwargs
    """
    def prepend_urls(self):
        return [
            re_path(
                #r"^(?P<resource_name>%s)/(?P<type>[\w\d_.-]+)/$"
                r"^(?P<resource_name>%s)/(?P<type>[\w\d_.-]+)/(?P<commune>[\w\d_.-]+)/(?P<name>[\w\d_.-]+)/$"
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
        effectorNodes = directory_effectors(directory)
        effectors = createEffectorRessources(request, effectorNodes)
        return effectors

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        logger.debug(f"!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!{bundle.request.GET.__dict__=}\n{kwargs=}!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!n")
        uid=find_effector_uid(kwargs["type"],kwargs["commune"],kwargs["name"])
        logger.debug(f"!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!{uid=}\n!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!n")
        directory=get_directory(bundle.request)
        try :
            effector = find_effector(directory, kwargs["type"], kwargs["commune"], kwargs["name"])
            logger.debug(effector)
            return createEffectorRessource(bundle.request, effector)
        except Exception as e : 
            raise Exception(f'Cannot find Effector {kwargs["type"]},{kwargs["commune"]},{kwargs["name"]} {e}')