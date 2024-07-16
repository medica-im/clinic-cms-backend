from django.utils.text import slugify
import neomodel
from datetime import datetime
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
    help = 'Deactivate Entry nodes.'
    
    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )
    
    def error(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def success(self, message):
        self.stdout.write(
            self.style.SUCCESS(message)
        )
    
    def add_arguments(self, parser):
        parser.add_argument(
            'uid',
            type=str,
            help='Entry uid'
        )
        parser.add_argument(
            '--reason',
            default='autre',
            const='autre',
            nargs='?',
            choices=[
                "décès", "déménagement", "raison médicale", "retraite",
                "changement d'activité", "autre"
            ],
            help='reason for deactivation (choices: %(choices)s)'
        )

    def handle(self, *args, **options):
        try:
            entry=Entry.nodes.get(uid=options["uid"])
        except Exception as e:
            self.error(e)
            return
        results, _meta = db.cypher_query(
            f"""MATCH (entry:Entry)
            WHERE entry.uid = '{entry.uid}'
            SET entry += {{active: false, deactivation_datetime: apoc.date.toISO8601(datetime().epochMillis), deactivation_reason: '{options['reason']}'}}
            RETURN entry;"""
        )
        if results:
            self.warn(f"{results=}")
        try:
            entry=Entry.nodes.get(uid=options["uid"])
        except neomodel.DoesNotExist as e:
            self.error(e)
            return
        if not entry.active:
            self.success(f'Entry {entry} was deactivated.')
        else:
            self.error(f'Entry {entry} was NOT deactivated!')
