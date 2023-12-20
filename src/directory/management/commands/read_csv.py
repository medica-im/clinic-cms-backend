from django.utils.text import slugify
import csv
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet
from facility.models import Organization
from directory.models import Slug, EffectorFacility
from django.db import DatabaseError, IntegrityError
from neomodel import db

import logging

logger = logging.getLogger(__name__)




class Command(BaseCommand):
    help = 'read csv'
    
    def fix(self, current_uid, correct_uid):
        query=f"""MATCH (e:Effector)-[rel:LOCATION]-(f:Facility)
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
        parser.add_argument('filename', type=str)        

    def handle(self, *args, **options):
        filename: str = options['filename']
        with open(filename, newline='') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in spamreader:
                if not row:
                    continue
                print(row[0] + ', ' + row[1])
                current_uid=row[1]
                self.warn(f'{current_uid=}')
                correct_uid=row[0]
                self.warn(f'{correct_uid=}')
                self.fix(current_uid, correct_uid)
                