from django.utils.text import slugify
import neomodel
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from access.models import Role as SqlRole
from access.neomodels import Role as NeoRole
import uuid
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recreate Postgres Access Roles as neo4j Role nodes'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        for sql_role in SqlRole.objects.all():
            neo_role = NeoRole()
            for attr in [
                "name",
                "label_fr",
                "label_en",
                "description_fr",
                "description_en",
            ]:
               value = getattr(sql_role, attr, None)
               setattr(neo_role, attr, value)
            try:
                neo_role.save()
            except neomodel.exceptions.UniqueProperty:
                self.warn(
                    f'A Role node with name = "{neo_role.name}" already exists'
                )
                continue
            self.warn(f"Created: {neo_role.__dict__}")

        all_nodes=NeoRole.nodes.all()
        self.warn(
            f"{len(all_nodes)} neo4j roles: {all_nodes}\n"
        )