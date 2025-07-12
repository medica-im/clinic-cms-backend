import uuid
import logging
from django.core.management.base import BaseCommand, CommandError
from directory.models.graph import (
    Entry,
    Effector,
    EffectorType,
    Facility,
    Directory,
)
import uuid
from directory.utils import add_label

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
            '--effector',
            type=str,
            help='Effector uid'
        )
        parser.add_argument(
            '--type',
            type=str,
            help="EffectorType uid"
        )
        parser.add_argument(
            '--dir',
            type=str,
            help="Directory name"
        )
        parser.add_argument(
            '--facility',
            type=str,
            help="Facility uid"
        )
        
    def handle(self, *args, **options):
        effector_uid=options["effector"]
        try:
            effector = Effector.nodes.get(uid=effector_uid)
        except Exception as e:
            raise e
        facility_uid=options["facility"]
        try:
            facility=Facility.nodes.get(uid=facility_uid)
        except Exception as e:
            raise e
        type_uid=options["type"]
        try:
            effector_type=EffectorType.nodes.get(uid=type_uid)
        except Exception as e:
            raise e
        try:
            directory=Directory.nodes.get(name=options["dir"])
        except Exception as e:
            raise e
        entry=Entry()
        entry.save()
        entry.effector_type.connect(effector_type)
        entry.facility.connect(facility)
        entry.effector.connect(effector)
        directory.entries.connect(entry)
        self.warn(
            f'{entry}\n{entry.__dict__}'
        )