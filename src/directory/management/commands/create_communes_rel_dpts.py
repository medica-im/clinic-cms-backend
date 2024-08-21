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
        name,
        slug
    ):
        try:
            node=Commune(
                name_fr=name,
                slug_fr=slug
            ).save()
            self.new_count+=1
            logger.debug(f'new node: {node=}')
        except Exception as e:
            self.warn(e)
        return node
 
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    """
    data = {
                'wikidata': [],
                'department_label': [],
                'commune_label': []
            }
    """

    def get_commune_df(self, name):
        mask = (
            (self.df_commune2024["TYPECOM"] == "COM")
            &
            (self.df_commune2024["LIBELLE"] == name)
        )
        df = self.df_commune2024[mask]
        return df

    def has_homonym(self, name):
        mask = (
            (self.df_commune2024["TYPECOM"] == "COM")
            &
            (self.df_commune2024["LIBELLE"] == name)
        )
        return len(self.df_commune2024[mask]) > 1

    def add_dpt_rel_to_existing_communes(self):
        for c in Commune.nodes.all():
            if c.department:
                self.already_linked+=1
                continue
            name=c.name_fr
            print(name)
            if self.has_homonym(name):
                self.homonyms.append(name)
                continue
            df = self.get_commune_df(name)
            print(df)
            if len(df)==0:
                msg=f"Commune {name} not found check name for typo"
                self.warn(msg)
                self.errors.append(msg)
            dpt_code=df.iloc[0]["DEP"]
            self.warn(f"{dpt_code=}")
            dpt = DepartmentOfFrance.nodes.get(code=dpt_code)
            self.warn(f"{dpt=}")
            c.department.connect(dpt)
            c.save()
            self.existing_linked += 1
        self.warn(
            f"New relationships created for existing communes: {self.existing_linked}\n"
            f"total existing communes: {len(Commune.nodes.all())}\n"
            f"not processed: {len(Commune.nodes.all()) - (self.already_linked + self.existing_linked)}\n"
            f"Homonyms:{self.homonyms}\n"
            f"Already linked:{self.already_linked}\n"
        )

    def create_new_communes_and_rel(self):
        mask = self.df_commune2024["TYPECOM"] == "COM"
        df = self.df_commune2024[mask]
        self.warn(f"We will try to create up to {len(df)} communes.")
        for index, row in df.iterrows():
            name=row["LIBELLE"]
            dpt_code=row["DEP"]
            try:
                c=Commune.nodes.get(name_fr=name)
                deps = [dep.code for dep in c.department.all()]
                if dpt_code in deps:
                    continue
            except:
                pass
            slug=slugify(name)
            try:
                dpt=DepartmentOfFrance.nodes.get(code=dpt_code)
            except Exception as e:
                self.errors.append(f'Dpt {dpt_code} not found. {e}')
                continue
            commune = self.create_node(name, slug)
            commune.department.connect(dpt)
            commune.save()
        self.warn(f"New Commune nodes created: {self.new_count}\n")

    def handle(self, *args, **options):
        self.new_count = 0
        self.errors = []
        self.already_linked = 0
        self.existing_linked = 0
        self.homonyms = []
        path_wd_dep = Path('directory/data/wd_dep.csv')
        path_commune2024 = Path('directory/data/v_commune_2024.csv')
        path_dts_of_france = Path('directory/data/departments_of_france.csv') 
        self.df_wd_dep = pd.read_csv(path_wd_dep)
        self.df_dpts= pd.read_csv(path_dts_of_france)
        self.df_commune2024 = pd.read_csv(path_commune2024)
        self.add_dpt_rel_to_existing_communes()
        self.create_new_communes_and_rel()
        self.warn(
            f"{len(self.errors)} errors:\n"
        )
        for e in self.errors:
            self.warn(
                f"{e}\n"
            )