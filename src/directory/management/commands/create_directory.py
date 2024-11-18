import neomodel
import sys
from django.core.management.base import BaseCommand, CommandError
from directory.models import Organization
from directory.models.graph import Directory

from neomodel import Q
import uuid

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create Directory node on neo4j and connect it to its Organization'

    def create_node(
        self,
        name,
        org_node
    ):
        try:
            node=Directory(
                name=name
            ).save()
        except Exception as e:
            self.warn(e)
            return
        node.organization.connect(org_node)
        return node

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        parser.add_argument('name', type=str)
        parser.add_argument('--organization', type=str)

    def handle(self, *args, **options):
        if not (len(sys.argv) > 2):
            return
        dir_name=options['name']
        org_arg=options['organization']
        org_node=None
        try:
            org_node = Organization.nodes.get(uid=org_arg)
        except neomodel.DoesNotExist as e:
            self.warn(f'{e}')
            try:
                org_node = Organization.nodes.get(name=org_arg)
            except neomodel.DoesNotExist as e:
                self.warn(f'{e}')
        if not org_node:
            self.warn(f'Organization with name or uid {org_arg} not found.')
            return
        if dir_name:
            try:
                node = Directory.nodes.get(name=dir_name)
                node.organization.connect(org_node)
            except neomodel.DoesNotExist:
                node = self.create_node(dir_name, org_node)
            self.warn(
                f'new Directory node: {node} owned by {node.organization.all()}'
            )