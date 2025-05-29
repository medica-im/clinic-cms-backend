import requests
from django.core.management.base import BaseCommand, CommandError
import neomodel
from neomodel.contrib.spatial_properties import NeomodelPoint
from directory.models import (
    Effector,
    HCW,
    EffectorType,
    Commune,
    Organization,
    OrganizationType,
    Facility,
)

class Command(BaseCommand):
    help = 'Update Facility nodes on neo4j: add address, GPS coordinates'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('facility', type=str)
        parser.add_argument('--url', required=True, type=str)

    def handle(self, *args, **options):
        facility_uid=options["facility"]
        url=options["url"]
        if facility_uid:
            try:
                nodes = [Facility.nodes.get(uid=facility_uid, lazy=True)]
            except:
                raise CommandError(f'No node found for uid="{facility_uid}"')
        else:
            nodes = Facility.nodes.all(lazy=True)
        for node in nodes:
            node=Facility.inflate(node)
            url=f"{url}/{node.uid}"
            try:
                r = requests.get(url, timeout=1, verify=True)
                r.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                print("HTTP Error")
                print(errh.args[0])
            except requests.exceptions.ReadTimeout as errrt:
                print("Time out")
            except requests.exceptions.ConnectionError as conerr:
                print("Connection error")
            except requests.exceptions.RequestException as errex:
                print("Exception request")
            f=r.json()
            node.building=f["address"]["building"]
            node.street=f["address"]["street"]
            node.geographical_complement=f["address"]["geographical_complement"]
            node.zip=f["address"]["zip"]
            node.zoom=f["address"]["zoom"]
            lng_lat=(f["address"]["longitude"], f["address"]["latitude"])
            node.location=NeomodelPoint(lng_lat, crs='wgs-84')
            node.save()