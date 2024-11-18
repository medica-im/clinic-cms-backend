import sys
from django.utils.text import slugify
import neomodel
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models import (
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    OrganizationType,
    Facility,
    Website,
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
    help = 'Create EffectorType node on neo4j'

    def create_node(
        self,
        label_fr,
        label_en,
        name_fr,
        name_en,
        slug_fr,
        slug_en,
        definition_fr,
        definition_en,
        synonyms_fr,
        synonyms_en,
    ):
        node=None
        created=False
        try:
            node=EffectorType(
                label_fr=label_fr,
                label_en=label_en,
                name_fr=name_fr,
                name_en=name_en,
                slug_fr=slug_fr,
                slug_en=slug_en,
                definition_fr=definition_fr,
                definition_en=definition_en,
                synonyms_fr=synonyms_fr,
                synonyms_en=synonyms_en,
            ).save()
            created=True
        except Exception as e:
            self.warn(e)
            node=EffectorType.nodes.filter(
                Q(label_en=label_en)
                | Q(label_fr=label_fr)
                | Q(name_en=name_en)
                | Q(name_fr=name_fr)
            )[0]
        if node and isinstance(node, EffectorType):
            logger.debug(f'{"new" if created else ""} node: {node=}')
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('--label_fr', type=str)
        parser.add_argument('--label_en', type=str)   
        parser.add_argument('--name_fr', type=str)
        parser.add_argument('--name_en', type=str)
        parser.add_argument('--slug_fr', type=str)
        parser.add_argument('--slug_en', type=str)
        parser.add_argument('--definition_fr', type=str)
        parser.add_argument('--definition_en', type=str)
        parser.add_argument('--synonyms_fr', nargs="*", default = None)
        parser.add_argument('--synonyms_en', nargs="*", default = None)

    def handle(self, *args, **options):
        if not (len(sys.argv) > 2):
            return
        label_fr=options['label_fr']
        if not label_fr:
            label_fr = options['name_fr']
        label_en=options['label_en']
        if not label_en:
            label_en = options['name_en']
        effector_type = self.create_node(
            label_fr=label_fr,
            label_en=options['label_en'] or options['name_en'],
            name_fr=options['name_fr'],
            name_en=options['name_en'],
            slug_fr=options['slug_fr'] or slugify(options['name_fr']),
            slug_en=options['slug_en'] or slugify(options['name_en']),
            definition_fr=options['definition_fr'],
            definition_en=options['definition_en'],
            synonyms_fr=options['synonyms_fr'],
            synonyms_en=options['synonyms_en'],
        )
        msg = (
            f"name_fr: {effector_type.name_fr}\n"
            f"label_fr: {effector_type.label_fr}\n"
            f"uid: {effector_type.uid}\n"
            f"slug_fr: {effector_type.slug_fr}\n"
            f"definition_fr: {effector_type.definition_fr}\n"
            f"synonyms_fr: {effector_type.synonyms_fr}\n"
        )
        self.warn(
            msg
        )