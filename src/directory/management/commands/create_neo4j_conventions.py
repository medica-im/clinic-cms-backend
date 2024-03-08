from django.utils.text import slugify
import neomodel
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from workforce.models import Convention as SqlConvention
from directory.models import Convention as NeoConvention
import uuid
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recreate Postgres Convention objects as neo4j Convention nodes'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        for sql_conv in SqlConvention.objects.all():
            neo_conv = NeoConvention()
            for attr in [
                "name",
                "label",
                "definition",
            ]:
               value = getattr(sql_conv, attr, None)
               setattr(neo_conv, attr, value)
            try:
                neo_conv.save()
            except neomodel.exceptions.UniqueProperty:
                self.warn(
                    f'A Role node with name = "{neo_conv.name}" already exists'
                )
                continue
            self.warn(f"Created: {neo_conv.__dict__}")

        all_nodes=NeoConvention.nodes.all()
        self.warn(
            f"{len(all_nodes)} neo4j roles: {all_nodes}\n"
        )