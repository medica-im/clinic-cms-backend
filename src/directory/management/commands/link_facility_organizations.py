import neomodel
import logging
from django.core.management.base import BaseCommand
from directory.models.graph import Facility, Entry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'For each Facility, find its owning organization Entry via '
        'Facility<-HAS_FACILITY-Entry<-HAS_ENTRY-Directory-OWNED_BY->OrgEntry '
        'and connect the Facility to OrgEntry via PART_OF.'
    )

    def handle(self, *args, **options):
        query = """
        MATCH (f:Facility)<-[:HAS_FACILITY]-(e:Entry {active: true})<-[:HAS_ENTRY]-(d:Directory)-[:OWNED_BY]->(org:Entry)
        RETURN DISTINCT f.uid AS facility_uid, org.uid AS org_entry_uid
        """
        results, _ = neomodel.db.cypher_query(query)
        if not results:
            self.stdout.write(self.style.WARNING('No Facility->OrgEntry pairs found.'))
            return
        connected = 0
        skipped = 0
        errors = 0
        for row in results:
            facility_uid, org_entry_uid = row
            try:
                facility_node = Facility.nodes.get(uid=facility_uid)
            except neomodel.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        f'Facility "{facility_uid}" not found, skipping.'
                    )
                )
                errors += 1
                continue
            try:
                org_entry_node = Entry.nodes.get(uid=org_entry_uid)
            except neomodel.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        f'Org Entry "{org_entry_uid}" not found, skipping.'
                    )
                )
                errors += 1
                continue
            if facility_node.organizations.is_connected(org_entry_node):
                self.stdout.write(
                    self.style.WARNING(
                        f'Facility {facility_uid} already PART_OF Entry {org_entry_uid}, skipping.'
                    )
                )
                skipped += 1
            else:
                facility_node.organizations.connect(org_entry_node)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Connected Facility {facility_uid} -> PART_OF -> Entry {org_entry_uid}'
                    )
                )
                connected += 1
        self.stdout.write(
            f'\nDone: {connected} connected, {skipped} already linked, {errors} errors.'
        )
