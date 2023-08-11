from tastypie import fields
import logging
from directory.utils import directory_effectors, get_directory
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from django.urls import re_path
from directory.models import Effector
from tastypie.utils import (
    is_valid_jsonp_callback_value, string_to_python,
    trailing_slash,
)
from directory.utils import (
    get_addresses,
    get_phones,
)

logger=logging.getLogger(__name__)

# We need a generic object to shove data in/get data from.
# Riak generally just tosses around dictionaries, so we'll lightly
# wrap that.

class EffectorObj(object):
    def __init__ (
            self,
            label_fr,
            name_fr,
            uid,
            types,
            communes,
            addresses,
            phones,
        ):
        self.label_fr = label_fr
        self.name_fr = name_fr
        self.uid = uid
        self.types = types
        self.communes = communes
        self.addresses = addresses
        self.phones = phones


def createEffectorRessources(request, nodes):
    data= []
    for node in nodes:
        label_fr = node.label_fr
        name_fr = node.name_fr
        uid = node.uid
        types = node.types
        communes = node.communes
        addresses = get_addresses(request, node)
        phones = get_phones(request, node)
        effector = EffectorObj(
            label_fr,
            name_fr,
            uid,
            types,
            communes,
            addresses,
            phones
        )
        data.append(effector)
    return data

class MessageResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    label_fr = fields.CharField(attribute='label_fr')
    name_fr = fields.CharField(attribute='name_fr')
    types = fields.ListField(attribute='types')
    communes = fields.ListField(attribute='communes')
    addresses = fields.ListField(attribute='addresses')
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
            effector = createEffectorRessources([effectorNode])
            return effector[0]
        except Exception as e : 
            raise Exception(f"Can't find Effector {uid}")