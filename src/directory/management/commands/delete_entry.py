from django.utils.text import slugify
import neomodel
import argparse
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models.graph import (
    Entry,
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    Facility,
    Directory,
    EffectorFacility,
)
from neomodel import Q, db
import uuid
import argparse

from django.conf import settings

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Delete Entry nodes automagically.'
    
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )
    
    def error(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )
    
    def add_arguments(self, parser):
        parser.add_argument(
            'uid',
            type=str,
            help='Entry uid'
        )

    
    def handle(self, *args, **options):
        try:
            entry=Entry.nodes.get(uid=options["uid"])
        except Exception as e:
            self.error(e)
            return
        self.warn(f'Deleting {entry}...')
        results, _meta = db.cypher_query(
            f"""MATCH (entry:Entry)-[rel]-()
            WHERE entry.uid = '{entry.uid}'
            DELETE rel;"""
        )
        if results:
            self.warn(f"{results=}")
        results, _meta = db.cypher_query(
            f"""MATCH (entry:Entry)
            WHERE entry.uid = '{entry.uid}'
            DETACH DELETE entry;"""
        )
        if results:
            self.warn(f"{results=}")
        try:
            entry=Entry.nodes.get(uid=options["uid"])
            if entry:
                self.error(f"entry {entry.uid} still exists...")
        except neomodel.DoesNotExist as e:
            self.error(e)
            self.warn(f'entry {entry.uid} was deleted!')