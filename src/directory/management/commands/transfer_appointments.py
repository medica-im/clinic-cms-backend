from django.utils.text import slugify

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet
from addressbook.models import Appointment as _Appointment
from directory.models.graph import Appointment, HouseCall, Office, Entry
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
        old_count = len(_Appointment.objects.all())
        new_count = 0 
        for _a in _Appointment.objects.all():
            try:
                neomodel_uid=_a.contact.neomodel_uid
            except ValueError:
                neomodel_uid=None
            if neomodel_uid:
                self.notice(f"{_a=}")
                to_continue=False
                try:
                    entry: Entry = Entry.nodes.get(uid=neomodel_uid.hex)
                except:
                    self.warn(f"Entry not found for uid={neomodel_uid}. Skipping...")
                    continue
                for a in entry.appointments.all():
                    if (a.phone and a.phone == _a.phone) or (a.url and a.url == _a.url):
                        to_continue=True
                        self.warn("Object is already transfered. Skipping...")
                if to_continue:
                    continue
                if _a.house_call:
                    a = HouseCall(phone=_a.phone or None, url=_a.url or None)
                else:
                    a = Appointment(phone=_a.phone or None, url=_a.url or None)
                a.save()
                entry.appointments.connect(a)
                new_count+=1
                self.notice(f"New node: {a} with labels {a.labels()}")
            else:
                continue
        self.notice(f"Old Appointment objects: {old_count}.\nNew nodes:  {new_count}.\nDone.")