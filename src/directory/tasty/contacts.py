from tastypie import fields
import logging
import json
from directory.utils import directory_contacts, get_directory
from tastypie.authorization import Authorization
from tastypie.resources import Resource, NamespacedModelResource

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
from directory.tasty.types import createEffectorTypeResources
from django.core.cache import cache
from django.conf import settings

logger=logging.getLogger(__name__)

# We need a generic object to shove data in/get data from.
# Riak generally just tosses around dictionaries, so we'll lightly
# wrap that.

class ContactObj(object):
    def __init__ (
            self,
            uid,
            timestamp,
        ):

        self.uid = uid
        self.timestamp = timestamp

def createContactResources(request, nodes):
    data= []
    for node in nodes:
        data.append(
            ContactObj(
                node['uid'],
                node["timestamp"]
            )
        )
    return data

class ContactResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    timestamp = fields.IntegerField(
        attribute='timestamp',
        default=0,
        readonly=True
    )

    class Meta:
        resource_name = 'contacts'
        allowed_methods=['get'] 
        collection_name = "contacts"
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
        contacts = directory_contacts(directory)
        contact_objects = createContactResources(request, contacts)
        return contact_objects

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        directory=get_directory(bundle.request)
        logger.debug(f'{directory=}')
        try :
            effectorNodes = directory_contacts(directory, uid)
            effector = createContactResources(bundle.request, effectorNodes)
            return effector[0]
        except Exception as e : 
            raise Exception(f"Can't find Contact {uid} {e}")