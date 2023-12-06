from django.utils.text import slugify
import neomodel
import uuid
import argparse
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
)
from addressbook.models import Contact, PhoneNumber
from neomodel import Q, db
import uuid
from directory.utils import add_label
import argparse

from django.conf import settings

import logging

logger = logging.getLogger(__name__)

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

class Command(BaseCommand):
    help = 'Add fields to CareHome / Effector node on neo4j'
    
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )
    
    def add_arguments(self, parser):
        parser.add_argument(
            'uid',
            type=str
        )
        parser.add_argument(
            '--regular_permanent',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--regular_temporary',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--alzheimer_permanent',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--alzheimer_temporary',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--uvpha_permanent',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--uhr_permanent',
            type=int,
            help="an integer in the range 0..1000"
        )
        parser.add_argument(
            '--day_care',
            type=int,
            help="an integer in the range 0..1000"
        )
        
    def handle(self, *args, **options):
        node_uid=options["uid"]
        self.warn(f"{options['regular_permanent']=}")
        try:
            effector = Effector.nodes.get(uid=node_uid)
        except Exception as e:
            self.warn(e)
            return
        effector.regular_permanent_bed=options['regular_permanent']
        effector.regular_temporary_bed=options['regular_temporary']
        effector.alzheimer_permanent_bed=options['alzheimer_permanent']
        effector.alzheimer_temporary_bed=options['alzheimer_temporary']
        effector.uvpha_permanent_bed=options['uvpha_permanent']
        effector.uhr_permanent_bed=options['uhr_permanent']
        effector.day_care=options['day_care']
        effector.save()
        self.warn(f'{effector}\n{effector.__dict__}')