import logging
from tastypie import fields
from tastypie.authorization import Authorization
from tastypie.resources import Resource
from tastypie.bundle import Bundle
from django.urls import re_path
from directory.models import EffectorType, Label
from tastypie.utils import (
    is_valid_jsonp_callback_value,
    string_to_python,
    trailing_slash,
)

from django.conf import settings

logger=logging.getLogger(__name__)

def flex_effector_type_label(
        effector,
        effector_type,
        request,
    ):
    try:
        effector_type_label=Label.get_label(
            effector_type.uid,
            effector.gender,
            "S",
            settings.LANGUAGE_CODE
        )
    except:
        effector_type_label=None
    effector_type.label = effector_type_label or effector_type.name
    return effector_type


class EffectorTypeObj(object):
    def __init__ (
            self,
            uid,
            label,
            name,
            slug,
            synonyms,
            definition,
        ):
        self.uid = uid
        self.label = label
        self.name = name
        self.slug = slug
        self.synonyms = synonyms
        self.definition = definition

def createEffectorTypeResources(request, nodes):
    data= []
    for node in nodes:
        uid = node.uid
        label = getattr(
            node,
            f'label_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'label_en',
                None
            )
        )
        name = getattr(
            node,
            f'name_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'name_en',
                None
            )
        )
        slug = getattr(
            node,
            f'slug_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'slug_en',
                None
            )
        )
        synonyms = getattr(
            node,
            f'synonyms_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'synonyms_en',
                None
            )
        )
        definition = getattr(
            node,
            f'definition_{settings.LANGUAGE_CODE}',
            getattr(
                node,
                'definition_en',
                None
            )
        )
        effector_type = EffectorTypeObj(
            uid,
            label,
            name,
            slug,
            synonyms,
            definition
        )
        data.append(effector_type)
    return data


class EffectorTypeResource(Resource):
    # Just like a Django ``Form`` or ``Model``, we're defining all the
    # fields we're going to handle with the API here.
    uid = fields.CharField(attribute='uid')
    label = fields.CharField(attribute='label')
    name = fields.CharField(attribute='name')
    slug = fields.CharField(attribute='slug')
    synonyms = fields.ListField(
        attribute='synonyms',
        null=True
    )
    definition = fields.CharField(
        attribute='definition',
        null=True
    )

    class Meta:
        resource_name = 'effector_types'
        allowed_methods=['get']
        collection_name = "effector_types"
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
        nodes = EffectorType.nodes.all()
        effector_types = createEffectorTypeResources(request, nodes)
        return effector_types

    def obj_get_list(self, bundle, **kwargs):
        return self.get_object_list(bundle.request)

    def obj_get(self, bundle, **kwargs):
        uid= kwargs['uid']
        try :
            node = EffectorType.nodes.get(uid=uid)
            effector_type = createEffectorTypeResources([node])
            return effector_type[0]
        except Exception as e:
            raise Exception(f"{e}\nCan't find EffectorType {uid}")
