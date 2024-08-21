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
        errors=[]
        name_idx=None
        department_code_idx=None
        type_idx=None
        with open('directory/data/v_commune_2024.csv') as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            commune = None
            for row in csv_reader:
                if line_count == 0:
                    print(f'Column names: {", ".join(row)}')
                    name_idx=row.index("LIBELLE")
                    department_code_idx=row.index("DEP")
                    type_idx=row.index("TYPECOM")
                    print(f'Indexes: {name_idx=}\t {department_code_idx=}')
                    line_count += 1
                else:
                    print(f'{row[0]}\t{row[1]}\t{row[2]}')
                    name=row[name_idx]
                    code=row[department_code_idx]
                    typecom=row[type_idx]
                    if typecom != "COM":
                        continue
                    try:
                        commune = Commune.nodes.get(name_fr=name)
                    except neomodel.DoesNotExist as e:
                        self.warn(f'No node found for name_fr={name}')
                        errors.push(f"Error for node {name}: {e}")
                        continue
                    department=DepartmentOfFrance.nodes.get(code=code)
                    try:
                        commune.department.connect(department)
                    except Exception as e:
                        msg=f"Relationship [{commune}--{department}] error: {e}"
                        self.warn(msg)
                        errors.push(msg)
                        continue
                    line_count += 1
            print(f'Processed {line_count} lines.')
        self.warn(
            f"node(s) created: {self.new_count}\n"
            f"errors:\n {chr(10).join(errors)}"
        )