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
    help = 'Create Entry node'
    
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
            help='Effector uid'
        )
        parser.add_argument(
            '--type',
            type=str,
            help="If Effector has more than 1 type, specify its uid"
        )
        parser.add_argument(
            '--dir',
            type=str,
            help="Directory name"
        )
        parser.add_argument(
            '--facility',
            type=str,
            help="If Effector has more than 1 facility, specify its uid"
        )
        
    def handle(self, *args, **options):
        effector_uid=options["uid"]
        try:
            effector = Effector.nodes.get(uid=effector_uid)
        except Exception as e:
            self.error(e)
            return
        facility_uid=options["facility"]
        type_uid=options["type"]
        
        entry=Entry()
        entry.save()
        entry.refresh()
        entry.effector.connect(effector)
        entry.refresh()
        facility_count=len(effector.facility.all())
        if (facility_count > 1 and not facility_uid):
            self.warn(
                "Effector connected to more than 1 Facility, please provide "
                "Facility uid."
            )
            return
        if facility_count == 0 and not facility_uid:
            self.warn("Effector does not have a Facility. Please provide one.")
            return
        elif facility_count == 1 and not facility_uid:
            entry.facility.connect(effector.facility[0])
        else:
            try:
                facility=Facility.nodes.get(uid=facility_uid)
                entry.facility.connect(facility)
            except Exception as e:
                self.error(e)
                return
        type_count=len(effector.type.all())
        if (type_count > 1 and not type_uid):
            self.warn(
                "Effector connected to more than 1 EffectorType, please "
                "provide EffectorType uid."
            )
            return
        if type_count == 0 and not type_uid:
            self.warn(
                "Effector does not have an EffectorType. Please provide one."
            )
            return
        elif type_count == 1 and not type_uid:
            entry.effector_type.connect(effector.type[0])
        else:
            try:
                effector_type=EffectorType.nodes.get(uid=type_uid)
                entry.effector_type.connect(effector_type)
            except Exception as e:
                self.error(e)
                return
        try:
            directory=Directory.nodes.get(name=options["dir"])
            directory.entries.connect(entry)
        except Exception as e:
            self.error(e)
            return
        self.warn(
            f'{entry}\n{entry.effector[0].name_fr}\n{entry.__dict__}'
            
        )