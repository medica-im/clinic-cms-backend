from django.core.management.base import BaseCommand

from directory import neo4j_triggers


class Command(BaseCommand):
    help = (
        "Install the APOC timestamp triggers (directory/neo4j_triggers.py). "
        "For a database restored into an empty server, where the migrations "
        "that install them are already recorded as applied."
    )

    def handle(self, *args, **options):
        neo4j_triggers.install()
        self.stdout.write(f"installed: {', '.join(neo4j_triggers.TRIGGERS)}")
