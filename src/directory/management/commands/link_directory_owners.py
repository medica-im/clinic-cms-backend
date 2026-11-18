import logging
from django.core.management.base import BaseCommand
from facility.models import Organization
from directory.owner import Link, link_directory_owner

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'For each Django Directory with an Organization, connect the '
        'Neo4j Directory node to the Organization Entry via OWNED_BY. '
        'Saving an Organization already does it; this catches up on rows '
        'written without a save (QuerySet.update, raw SQL, loaddata).'
    )

    def handle(self, *args, **options):
        orgs = Organization.objects.select_related('directory').filter(
            directory__isnull=False,
            neomodel_uid__isnull=False,
        )
        for org in orgs:
            dir_name = org.directory.name
            entry_uid = org.neomodel_uid.hex
            result = link_directory_owner(dir_name, entry_uid)
            if result is Link.NO_DIRECTORY:
                self.stderr.write(
                    self.style.ERROR(
                        f'Neo4j Directory "{dir_name}" not found, skipping.'
                    )
                )
            elif result is Link.NO_ENTRY:
                self.stderr.write(
                    self.style.ERROR(
                        f'Neo4j Entry "{entry_uid}" not found for org "{org.name}", skipping.'
                    )
                )
            elif result is Link.EXISTED:
                self.stdout.write(
                    self.style.WARNING(
                        f'"{dir_name}" already owned by Entry {entry_uid}, skipping.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Connected Directory "{dir_name}" -> OWNED_BY -> Entry {entry_uid}'
                    )
                )
