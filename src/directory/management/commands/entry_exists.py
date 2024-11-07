from django.utils.text import slugify
import neomodel
from neomodel import db
import uuid
import argparse
from langcodes import *
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
    Facility,
    Directory,
    EffectorFacility,
    Convention,
    HealthWorker,
    Entry,
)
from directory.models.graph import Directory as NeoDirectory
from addressbook.models import Contact, PhoneNumber
from neomodel import Q, db
from directory.utils import add_label
from neomodel.exceptions import MultipleNodesReturned

from django.conf import settings

import logging
from directory.management.commands.care_home import is_valid_uuid

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check if an Entry node exists'
    
    def entry_exists(self, effector, effector_type, facility):
        query=f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility), 
        (entry)-[:HAS_EFFECTOR]->(e:Effector),
        (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        WHERE e.uid="{effector}"
        AND et.uid="{effector_type}"
        AND f.uid="{facility}"
        RETURN entry;"""
        results, meta = db.cypher_query(query, resolve_objects=True)
        self.warn(f"{results=}\n{meta=}")
        self.warn(str(bool(results)))
        return bool(results)

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('--effector', type=str)
        parser.add_argument('--type', type=str)
        parser.add_argument('--facility', type=str)
        
    def handle(self, *args, **options):
        answer = "yes" if self.entry_exists(
            options["effector"],
            options["type"],
            options["facility"]
        ) else "no"
        self.warn(answer)

