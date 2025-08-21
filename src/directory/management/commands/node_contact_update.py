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
            
    def test_is_facility(self, neomodel_uid: str):
        query=f"""MATCH (f:Facility) WHERE facility.uid="{neomodel_uid}" RETURN facility;"""
        q = db.cypher_query(query, resolve_objects = True)
        for row in q[0]:
            if row:
                return True


    def test_is_location(self, neomodel_uid: str, contact: Contact):
        query=f"""MATCH (f:Facility)<-[:HAS_LOCATION]-(entry:Entry)-[:HAS_EFFECTOR]->(e:Effector)-[rel:LOCATION]-(f:Facility)
        WHERE rel.uid="{neomodel_uid}"
        RETURN entry;"""
        q = db.cypher_query(query, resolve_objects = True)
        if len(q[0])>1:
            self.warn(f"The location {neomodel_uid} corresponds to more than one Entry node. Skipping...")
            return False
        for row in q[0]:
            (entry,) = row
            contact.neomodel_uid=entry.uid
            contact.save()
            return True

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
        empty_count = 0
        facility_count = 0
        location_count = 0
        location_updated_count = 0
        for contact in Contact.objects.all():
            neomodel_uid=contact.neomodel_uid
            if not neomodel_uid:
                empty_count+=1
                continue
            if neomodel_uid:
                if self.test_is_entry(neomodel_uid.hex):
                    self.warn(f"{contact} neomodel node is an Entry.")
                    entry_count+=1
                    continue
                if self.test_is_facility(neomodel_uid.hex):
                    self.warn(f"{contact} neomodel node is a Facility.")
                    facility_count+=1
                    continue
                if self.test_is_location(neomodel_uid.hex, contact):
                    self.warn(f"{contact} neomodel node is a Facility.")
                    location_updated_count+=1
                    location_count+=1
                    continue
                else:
                    location_count+=1
        self.warn(
            f'There are {total} Contact records.\n'
            f'{empty_count} of those have an empty neomodel_uid field.\n'
            f'{entry_count} of those have a neomodel_uid field linked to an Entry node.\n'
            f'{location_count} of those had a neomodel_uid field linked to a LOCATION relationship.\n'
            f'{location_updated_count} contacts with location relationship uid have been updated to Entry node uid.'
        )
