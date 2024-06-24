from django.utils.text import slugify
import neomodel
import uuid
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
    help = 'Create Entry nodes automagically.'
    
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
            'dir',
            type=str,
            help='Directory name'
        )

    def add_to_not_processed(self, effector):
        new = not (effector.uid in [x.uid for x in self.not_processed])
        if new:
            self.not_processed.append(effector)

    def handle(self, *args, **options):
        try:
            directory=Directory.nodes.get(name=options["dir"])
        except Exception as e:
            self.error(e)
            return
        existing_effectors: [str] = []
        results, _meta = db.cypher_query(
            f"""MATCH (d:Directory)-[:HAS_ENTRY]->(entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector)
            WHERE d.name = '{directory.name}'
            RETURN effector;""",
            resolve_objects=True
        )
        if results:
            self.warn(f"{results=}")
            for result in results:
                effector_uid = result[0].uid
                if effector_uid not in existing_effectors:
                    existing_effectors.append(effector_uid)

        results, _meta = db.cypher_query(
            f"""MATCH (e:Effector)-[l:LOCATION]-(f:Facility)
            WHERE l.directories = ['{directory.name}']
            RETURN e;""",
            resolve_objects=True
        )
        if not results:
            return
        processed=[]
        self.not_processed=[]
        entries=[]
        self.warn(f"Processing {len(results)} effectors...\n")
        for result in results:
            effector=result[0]
            self.warn(f"{effector}\n")
            if effector.uid in existing_effectors:
                self.warn(f'{effector} already linked to an Entry: skipping...')
                self.not_processed.append(effector)
                continue
            if (
                not effector.type.all()
                or
                (effector.type.all() and len(effector.type.all())>1)
                or
                not effector.facility.all()
                or
                (effector.facility.all() and len(effector.facility.all())>1)
            ):
                self.add_to_not_processed(effector)
            else:
                entry=Entry()
                entry.save()
                entry.refresh()
                entry.effector.connect(effector)
                entry.refresh()
                entry.facility.connect(effector.facility[0])
                entry.effector_type.connect(effector.type[0])
                directory.entries.connect(entry)
                processed.append(effector)
                entries.append(entry)
        self.warn(
            f'{len(existing_effectors)} effectors already have an entry:\n'
            f'{existing_effectors=}\n\n'
            f"{len(self.not_processed)} effectors were not processed:\n"
            f"{[e.label_fr or e.name_fr or e.uid for e in self.not_processed]}\n\n"
            f"{len(processed)} effectors were processed:\n"
            f"{[e.uid for e in processed]}\n\n"
            f"{len(entries)} entries were created:\n"
            f"{[e.effector[0].label_fr or e.effector[0].name_fr or e.effector[0].uid for e in entries]}"
        )