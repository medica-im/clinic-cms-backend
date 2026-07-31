import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class EffectorTypeObj:
    def __init__(self, uid, label, name, slug, synonyms, definition, raw_label=None):
        self.uid = uid
        self.label = label
        self.raw_label = raw_label
        self.name = name
        self.slug = slug
        self.synonyms = synonyms
        self.definition = definition


def createEffectorTypeResources(node):
    uid = node.uid
    label = getattr(
        node,
        f'label_{settings.LANGUAGE_CODE}',
        getattr(node, 'label_en', None)
    )
    name = getattr(
        node,
        f'name_{settings.LANGUAGE_CODE}',
        getattr(node, 'name_en', None)
    )
    slug = getattr(
        node,
        f'slug_{settings.LANGUAGE_CODE}',
        getattr(node, 'slug_en', None)
    )
    synonyms = getattr(
        node,
        f'synonyms_{settings.LANGUAGE_CODE}',
        getattr(node, 'synonyms_en', None)
    )
    definition = getattr(
        node,
        f'definition_{settings.LANGUAGE_CODE}',
        getattr(node, 'definition_en', None)
    )
    return EffectorTypeObj(uid, label, name, slug, synonyms, definition, raw_label=label)


class CommuneObj:
    def __init__(self, uid, name, slug, wikidata):
        self.uid = uid
        self.name = name
        self.slug = slug
        self.wikidata = wikidata


def createCommuneResources(nodes):
    data = []
    for node in nodes:
        uid = node.uid
        name = getattr(
            node,
            f'name_{settings.LANGUAGE_CODE}',
            getattr(node, 'name_en', None)
        )
        slug = getattr(
            node,
            f'slug_{settings.LANGUAGE_CODE}',
            getattr(node, 'slug_en', None)
        )
        wikidata = getattr(node, 'wikidata')
        data.append(CommuneObj(uid, name, slug, wikidata))
    return data


