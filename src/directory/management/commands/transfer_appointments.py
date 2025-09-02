from django.utils.text import slugify

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet
from addressbook.models import Appointment
from directory.models import Slug
from django.db import DatabaseError, IntegrityError

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Transfer appointments from Postgres to Neo4j'

    def notice(self, message):
        self.stdout.write(
            self.style.NOTICE(message)
        )
    
    def warn(self, message):
        self.stdout.write(
            self.style. WARNING(message)
        )

    def add_arguments(self, parser):
        pass      

    def handle(self, *args, **options):
        for a in Appointment.objects.all():
            try:
                neomodel_uid=a.contact.neomodel_uid
            except ValueError:
                neomodel_uid=None
            if neomodel_uid:
                self.notice(f"{neomodel_uid.hex=}, {a.house_call=}")
