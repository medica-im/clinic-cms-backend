from django.utils.text import slugify
import csv
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet
from facility.models import Organization
from addressbook.models import Contact
from directory.models import Slug, EffectorFacility
from django.db import DatabaseError, IntegrityError
from neomodel import db

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Update neomodel_uid field in Contact objects to the Entry node uid.'

    def test_is_entry(self, neomodel_uid: str):
        query=f"""MATCH (entry:Entry) WHERE entry.uid="{neomodel_uid}" RETURN entry;"""
        q = db.cypher_query(query, resolve_objects = True)
        for row in q[0]:
            if row:
                return True

    def fix(self, current_uid, correct_uid):
        query=f"""MATCH (entry:Entry)-[:HAS_EFFECTOR]->(e:Effector)-[rel:LOCATION]-(f:Facility)
        WHERE rel.uid="{current_uid}"
        SET rel.uid="{correct_uid}"
        RETURN e,rel,f;"""
        results, cols = db.cypher_query(query)
        if results:
            for row in results:
                location=row[cols.index('rel')]
                self.warn(f'{location} is fixed.')

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        pass
        #parser.add_argument('filename', type=str)        

    def handle(self, *args, **options):
        total = len(Contact.objects.all())
        entry_count = 0
        for contact in Contact.objects.all():
            neomodel_uid=contact.neomodel_uid
            if neomodel_uid:
                if self.test_is_entry(neomodel_uid.hex):
                    self.warn(f"{contact} neomodel node is an Entry.")
                    entry_count+=1
        self.warn(
            f'There are {total} Contact records.\n'
            f'{entry_count} of thos have a neomodel_uid field linked ton an Entry node.\n'
        )
