import csv
from django.utils.text import slugify
from django.core.management.base import BaseCommand, CommandError
from directory.models import Country, RegionOfFrance, DepartmentOfFrance

class Command(BaseCommand):
    help = 'Create regions of France nodes on neo4j'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help="file path to csv file")
    
    def handle(self, *args, **options):
        path=options['path']
        file = open(path)
        csvreader = csv.reader(file)
        try:
            france = Country.nodes.get(code="FR")
        except:
            raise CommandError("Create France Country node")
        rows = []
        dpt_count=0
        rof_count=0
        for idx, row in enumerate(csvreader):
            if idx==0:
                continue
            code_departement=row[0]
            nom_departement=row[1]
            code_region=row[2]
            nom_region=row[3]
            try:
                dpt = DepartmentOfFrance.nodes.get(code=code_departement)
            except:
                raise CommandError(f"Department with code {code_departement} does not exist")
            try:
                rof = RegionOfFrance.nodes.get(code=code_region)
            except:
                rof = RegionOfFrance(
                    name=nom_region,
                    code=code_region,
                    slug=slugify(nom_region)
                ).save()
                if not rof.country.is_connected(france):
                    rof.country.connect(france)
                    rof_count+=1
            if not dpt.region.is_connected(rof):
                dpt.region.connect(rof)
                dpt_count+=1
        self.warn(
            f"Regions created: {rof_count}"
            f"Departments connected to their region: {dpt_count}\n"
        )