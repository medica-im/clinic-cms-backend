import neomodel
import logging
from django.core.management.base import BaseCommand
from facility.models import Organization
from directory.models.graph import Directory, Entry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'For each Django Directory with an Organization, connect the '
        'Neo4j Directory node to the Organization Entry via OWNED_BY.'
    )

    def handle(self, *args, **options):
        orgs = Organization.objects.select_related('directory').filter(
            directory__isnull=False,
            neomodel_uid__isnull=False,
        )
        for org in orgs:
            dir_name = org.directory.name
            entry_uid = org.neomodel_uid.hex
            try:
                dir_node = Directory.nodes.get(name=dir_name)
            except neomodel.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        f'Neo4j Directory "{dir_name}" not found, skipping.'
                    )
                )
                continue
            try:
                entry_node = Entry.nodes.get(uid=entry_uid)
            except neomodel.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        f'Neo4j Entry "{entry_uid}" not found for org "{org.name}", skipping.'
                    )
                )
                continue
            if dir_node.owner.is_connected(entry_node):
                self.stdout.write(
                    self.style.WARNING(
                        f'"{dir_name}" already owned by Entry {entry_uid}, skipping.'
                    )
                )
            else:
                dir_node.owner.connect(entry_node)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Connected Directory "{dir_name}" -> OWNED_BY -> Entry {entry_uid}'
                    )
                )
