from django.utils.text import slugify
import csv
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
    DepartmentOfFrance,
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

def wikidata_department():
    query=f"""
    SELECT ?item ?label 
    WHERE {{
    ?item wdt:P31 wd:Q6465;
    rdfs:label ?label.
    FILTER(LANG(?label) = "fr").
    FILTER NOT EXISTS{{ ?item wdt:P576 ?date }}
    }}
    """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
    cache.set(
        f"wikidata_department",
        df,
        WIKIDATA_TTL
    )
    return df

def get_wikidata_commune()->str:
    df = cache.get_or_set(
        f"wikidata_commune",
        lambda: wikidata_department(),
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
    help = 'Create all France department nodes on neo4j'

    def create_node(
        self,
        name,
        code,
        slug,
        wikidata
    ):
        try:
            node=DepartmentOfFrance(
                name=name,
                code=code,
                slug=slug,
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

    def handle(self, *args, **options):
        self.new_count = 0
        name_idx=None
        code_idx=None
        wikidata_idx=None
        with open('directory/data/departments_of_france.csv') as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0:
                    print(f'Column names: {", ".join(row)}')
                    name_idx=row.index("name")
                    code_idx=row.index("code")
                    wikidata_idx=row.index("wikidata")
                    print(f'Indexes: {name_idx=}\t {code_idx=}\t{wikidata_idx}')
                    line_count += 1
                else:
                    print(f'{row[0]}\t{row[1]}\t{row[2]}')
                    self.create_node(
                       row[name_idx],
                       row[code_idx],
                       slugify(row[name_idx]),
                       row[wikidata_idx]
                    )
                    line_count += 1
            print(f'Processed {line_count} lines.')
        self.warn(
            f"node(s) created: {self.new_count}\n"
        )