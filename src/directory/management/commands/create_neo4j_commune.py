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

"""
DROP CONSTRAINT constraint_unique_AdministrativeTerritorialEntityOfFrance_name_fr IF EXISTS
DROP CONSTRAINT constraint_unique_AdministrativeTerritorialEntityOfFrance_name_en IF EXISTS
DROP CONSTRAINT constraint_unique_AdministrativeTerritorialEntityOfFrance_slug_fr IF EXISTS
DROP CONSTRAINT constraint_unique_AdministrativeTerritorialEntityOfFrance_slug_en IF EXISTS
DROP CONSTRAINT constraint_unique_Commune_name_fr IF EXISTS
DROP CONSTRAINT constraint_unique_Commune_name_en IF EXISTS
DROP CONSTRAINT constraint_unique_Commune_slug_fr IF EXISTS
DROP CONSTRAINT constraint_unique_Commune_slug_en IF EXISTS
"""

def wikidata_commune():
    query="""
    SELECT ?item ?label 
    WHERE {
    ?item wdt:P31 wd:Q484170;
    rdfs:label ?label.
    FILTER(LANG(?label) = "fr").
    FILTER NOT EXISTS{ ?item wdt:P576 ?date }
    }
    """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
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
    help = 'Create all France Commune nodes on neo4j'

    def create_node(
        self,
        name_en,
        name_fr,
        slug_en,
        slug_fr,
        wikidata
    ):
        try:
            node=Commune(
                name_en=name_en,
                name_fr=name_fr,
                slug_en=slug_en,
                slug_fr=slug_fr,
                wikidata=wikidata
            ).save()
            self.new_count+=1
            logger.debug(f'new node: {node=}')
        except Exception as e:
            self.warn(e)
            
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('--lang',
                    default='fr',
                    const='fr',
                    nargs='?',
                    choices=['fr', 'en'],
                    help='language (default: %(default)s)'
        )

    def handle(self, *args, **options):
        self.new_count = 0
        df = wikidata_commune()
        row_count = int(df.count()['item'])
        for i in range(row_count):
            wikidata = df.loc[i]['item'].split("/")[-1]
            name_fr = df.loc[i]['label']
            name_en = None
            slug_fr = slugify(name_fr)
            slug_en = None
            self.create_node(
                name_en,
                name_fr,
                slug_en,
                slug_fr,
                wikidata
            )
        self.warn(
            f"node(s) created: {self.new_count}\n"
        )