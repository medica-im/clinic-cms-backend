import logging

from django.conf import settings
from django.urls import re_path

from tastypie import fields
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.fields import ForeignKey
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)

from directory.tasty.communes import createCommuneResources
from directory.serializers import display_tag_name
from directory.utils import (
    get_phones_neomodel,
    find_entry,
    directory_effectors,
    get_directory,
)
from directory.serializers import (
    ConventionSerializer,
    ThirdPartyPayerSerializer,
)
from directory.tasty.types import (
    createEffectorTypeResources,
    flex_effector_type_label
)
from directory.models import Label

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
            convention,
            carte_vitale,
            third_party_payers,
            payment_methods,
            rpps,
            adeli,
            spoken_languages,
            avatar,
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
        self.convention = convention
        self.carte_vitale = carte_vitale
        self.third_party_payers = third_party_payers
        self.payment_methods = payment_methods
        self.rpps = rpps
        self.adeli = adeli
        self.spoken_languages = spoken_languages
        self.avatar = avatar

def createEffectorRessource(request, node):
    location=node["location"]
    uid = location.uid
    effector_node=node["effector"]
    health_worker=node["health_worker"]
    address=node["address"]
    commune_node = node["commune"]
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
    effector_type_obj_lst = createEffectorTypeResources(request, [et])
    effector_type_obj=effector_type_obj_lst[0]
    effector_type_obj=flex_effector_type_label(
        effector_node,
        effector_type_obj,
        request
    )
    effector_type_dict=effector_type_obj.__dict__
    phones = node["phones"]
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
            location.contactUpdatedAt,
        ]
    )
    facility = {
        "uid": node["facility"].uid,
        "slug": node["facility"].slug,
        "name": node["facility"].name,
        "label": node["facility"].label or node["facility"].name
    }
    emails = node["emails"]
    websites = node["websites"]
    socialnetworks = node["socialnetworks"]
    appointments = node["appointments"]
    profile = node["profile"]
    # convention
    serializer = ConventionSerializer(effector_node.convention.all(), many=True)
    try:
        convention = serializer.data[0]
    except IndexError:
        convention = None
    # carte vitale
    carte_vitale = location.carteVitale
    #third party payer 
    serializer = ThirdPartyPayerSerializer(
        node["third_party_payers"],
        many=True
    )
    third_party_payers = serializer.data
    # payment_methods (reuse ThirdPartyPayerSerialize)
    serializer = ThirdPartyPayerSerializer(
        node["payment_methods"],
        many=True
    )
    payment_methods = serializer.data
    rpps=health_worker.rpps
    adeli=health_worker.adeli
    try:
        spoken_languages=[
            display_tag_name(t) for t in health_worker.spoken_languages
        ]
    except TypeError:
        spoken_languages = None
    avatar=node["avatar"]

    effector = EffectorObj(
        label,
        name,
        slug,
        uid,
        effector_uid,
        effector_type_dict,
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
        convention,
        carte_vitale,
        third_party_payers,
        payment_methods,
        rpps,
        adeli,
        spoken_languages,
        avatar,
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
    phones = fields.ListField(attribute='phones', null=True)
    facility = fields.DictField(attribute='facility')
    updatedAt = fields.IntegerField(attribute='updatedAt')
    emails = fields.ListField(attribute='emails', null=True)
    websites = fields.ListField(attribute='websites', null=True)
    socialnetworks = fields.ListField(attribute='socialnetworks', null=True)
    appointments = fields.ListField(attribute='appointments', null=True)
    profile = fields.DictField(attribute='profile', null=True)
    convention = fields.DictField(attribute='convention', null=True)
    carte_vitale = fields.BooleanField(attribute='carte_vitale', null=True)
    third_party_payers = fields.ListField(
        attribute='third_party_payers',
        null=True
    )
    payment_methods = fields.ListField(
        attribute='payment_methods',
        null=True
    )
    rpps = fields.CharField(attribute='rpps', null=True)
    adeli = fields.CharField(attribute='adeli', null=True)
    spoken_languages = fields.ListField(attribute='spoken_languages', null=True)
    avatar = fields.DictField(attribute='avatar', null=True)

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
                r"^(?P<resource_name>%s)/(?P<facility>[\w\d_.-]+)/(?P<type>[\w\d_.-]+)/(?P<name>[\w\d_.-]+)/$"
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
        #logger.debug(f"!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!{bundle.request.GET.__dict__=}\n{kwargs=}!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!n")
        #uid=find_effector_uid(kwargs["facility"],kwargs["type"],kwargs["name"])
        #logger.debug(f"!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!{uid=}\n!\n!\n!\n!\n!\n!!\n!\n!\n!\n!\n!n")
        directory=get_directory(bundle.request)
        try:
            effector = find_entry(directory, kwargs["facility"], kwargs["type"], kwargs["name"])
            return createEffectorRessource(bundle.request, effector)
        except Exception as e : 
            raise Exception(f'Cannot find Effector {kwargs["facility"]},{kwargs["type"]},{kwargs["name"]} {e}')