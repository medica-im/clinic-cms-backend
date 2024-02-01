from django.utils.text import slugify
import neomodel
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from django.db import DatabaseError, IntegrityError
from directory.models import (
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    OrganizationType,
    Facility,
)
from addressbook.models import Contact, Address
from access.models import Role

from neomodel import Q
import uuid
from addressbook.wikidata import WikiDataQueryResults
from django.core.cache import cache
from django.conf import settings
from rdflib.plugins.shared.jsonld.keys import NONE

WIKIDATA_TTL = 60 * 60           

import logging

logger = logging.getLogger(__name__)

def wikidata_commune():
    query=f"""
    SELECT ?item ?label 
    WHERE {{
    ?item wdt:P31 wd:Q484170;
    rdfs:label ?label.
    FILTER(LANG(?label) = "fr").
    }}
    """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
    cache.set(
        f"wikidata_commune",
        df,
        WIKIDATA_TTL
    )
    return df
    
def get_wikidata_commune()->str:
    df = cache.get_or_set(
        f"wikidata_commune",
        lambda: wikidata_commune(),
        WIKIDATA_TTL
    )
    return df

def wikidata(code: str, select: str, lang: str='FR'):
    """
    Get 2-letter country code from city wikidata code.
    """
    query=f"""
        SELECT ?label WHERE {{
        wd:{code} rdfs:label ?label .
        FILTER (langMatches( lang(?label), "{lang}" ) )
        }}
        """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
    cache.set(
        f"label_{code}",
        df.label[0],
        WIKIDATA_TTL
    )
    if select=="label":
        return df.label[0]

def get_label(code: str, lang: str)->str:
    label = cache.get_or_set(
        f"label_{code}",
        lambda: wikidata(code, "label", lang),
        WIKIDATA_TTL
    )
    return label

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def display_relationship(rel):
    return [
        c.name_fr or c.label_fr or c.concept_en
        for c in rel.all()
    ]

class Command(BaseCommand):
    help = 'Create Facility node on neo4j'

    def create_node(
        self,
        name_en,
        name_fr,
        slug_en,
        slug_fr,
        wikidata
    ):
        node=None
        created=False
        try:
            node=Commune(
                name_en=name_en,
                name_fr=name_fr,
                slug_en=slug_en,
                slug_fr=slug_fr,
                wikidata=wikidata
            ).save()
            created=True
        except Exception as e:
            self.warn(e)
        if node and isinstance(node, Commune):
            logger.debug(f'{"new" if created else ""} node: {node=}')
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('code', type=str)
        parser.add_argument('--lang',
                    default='fr',
                    const='fr',
                    nargs='?',
                    choices=['fr', 'en'],
                    help='language (default: %(default)s)'
        )
        parser.add_argument('--slug', type=str)

    def handle(self, *args, **options):
        code=options['code']
        slug=options['slug']
        try:
            commune=Commune.nodes.get(wikidata=code)
            self.warn(
                f'Commune {commune} already exists in the database.\n'
                f'{commune.__dict__}'
            )
            return
        except neomodel.DoesNotExist:
            pass
        lang=options['lang']
        if lang=='fr':
            name_fr = get_label(code, 'FR')
            name_en = None
            slug_fr = slug or slugify(name_fr)
            slug_en = None
        elif lang=='en':
            name_en = get_label(code, 'EN')
            name_fr = None
            slug_en = slug or slugify(name_en)
            slug_fr = None
        wikidata = code
        node = self.create_node(
            name_en,
            name_fr,
            slug_en,
            slug_fr,
            wikidata
        )
        self.warn(
            f"node: {node}\n"
            f"{node.__dict__}"
        )