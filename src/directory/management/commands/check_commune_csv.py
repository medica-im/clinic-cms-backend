from django.utils.text import slugify
import pandas as pd
from pathlib import Path
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
from directory.models.graph import DepartmentOfFrance

WIKIDATA_TTL = 60 * 60           

import logging

logger = logging.getLogger(__name__)

def wikidata(commune):
    query=f"""
    SELECT ?prop_val_label WHERE {{
    VALUES (?company) {{
      (wd:{commune})
    }}
    ?company ?prop_id ?company_item.
    ?company_item wdt:P31 wd:Q6465.
    ?wd wikibase:directClaim ?prop_id.
    ?wd rdfs:label ?prop_label.
    FILTER(?prop_id = wdt:P131)
    OPTIONAL {{
      ?company_item rdfs:label ?prop_val.
      FILTER((LANG(?prop_val)) = "fr")
    }}
    BIND(COALESCE(?prop_val, ?companyItem) AS ?prop_val_label)
    FILTER((LANG(?prop_label)) = "fr")
    }}
    """
    data_extracter = WikiDataQueryResults(query)
    df = data_extracter.load_as_dataframe()
    print(df)
    return df

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

    """
    data = {
                'wikidata': [],
                'department_label': [],
            }
    """

    def handle(self, *args, **options):
        path_wd_dep = Path('directory/data/wd_dep.csv')
        path_commune2024 = Path('directory/data/v_commune_2024.csv')
        path_dts_of_france = Path('directory/data/departments_of_france.csv') 
        df_wd_dep = pd.read_csv(path_wd_dep)
        print(df_wd_dep)
        df_dpts= pd.read_csv(path_dts_of_france)
        print(df_dpts)
        df_commune2024 = pd.read_csv(path_commune2024)
        self.errors = []
        for index, row in df_commune2024.iterrows():
            typecom = row["TYPECOM"]
            if typecom != "COM":
                continue
            name=row["LIBELLE"]
            dep_code=row["DEP"]
            mask = (df_dpts["code"] == dep_code)
            df= df_dpts[mask]
            if len(df)==0:
                self.warn(f"{df}")
                return
            try:
                dep_label = df.iloc[0]["name"]
            except KeyError:
                self.warn(f"{df}")
                return
            mask = (
                (df_wd_dep["department_label"] == dep_label)
                &
                (df_wd_dep["commune_label"] == name)
            )
            if len(df_wd_dep[mask]) == 0:
                self.warn(
                    f'"{name}" "{dep_label}" "{dep_code}"'
                )
                self.warn(
                    f'{df_wd_dep[mask]}'
                )
                self.errors.append(
                    f'{name} {dep_label} {dep_code}'
                )
        self.warn(
            f"{len(self.errors)=}\n"
        )
        for e in self.errors:
            self.warn(
                f"{e}\n"
            )