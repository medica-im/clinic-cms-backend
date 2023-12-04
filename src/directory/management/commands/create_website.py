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
    Website
)
from addressbook.models import Contact, Address
from access.models import Role

from neomodel import Q
import uuid
from addressbook.wikidata import WikiDataQueryResults
from django.core.cache import cache
from django.conf import settings
from rdflib.plugins.shared.jsonld.keys import NONE

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
    help = 'Create Website node on neo4j'

    def create_node(
        self,
        url,
    ):
        try:
            node=Website(
                url=url
            ).save()
        except Exception as e:
            self.warn(e)
            return
        self.warn(f'{"new" if created else ""} node: {node=}')
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('url', type=str)

    def handle(self, *args, **options):
        url_str=options['url']
        website=Website.nodes.get_or_none(url=url_str)
        if not website:
            website = self.create_node(url_str)
        self.warn(
            f"{website}\n"
            f"{website.__dict__}\n"
        )