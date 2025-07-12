import neomodel
import logging
from django.core.management.base import BaseCommand, CommandError
from directory.models.graph import Directory, Entry

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create Directory node on neo4j and connect it to its Entry owner'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('name', type=str)
        parser.add_argument('--owner', type=str, help="uid of Entry")

    def handle(self, *args, **options):
        dir_name=options['name']
        owner_uid=options['owner']
        if not dir_name:
            raise ValueError("Directory name cannot be empty")
        try:
            node = Directory.nodes.get(name=dir_name)
        except neomodel.DoesNotExist:
            node = Directory(name=dir_name)
            node.save()
        if owner_uid:
            try:
                owner = Entry.nodes.get(uid=owner_uid)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
                raise e
            node.owner.connect(owner)
        self.warn(
            f'new Directory node: {node} owned by {node.owner.all()}'
        )