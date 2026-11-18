from django.utils.text import slugify

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from directory.models import Slug
from django.db import DatabaseError, IntegrityError
from directory.models import MESH

from django.conf import settings

from neo4j import GraphDatabase

URI=settings.NEO4J_URI
AUTH=settings.NEO4J_AUTH
DATABASE=settings.NEO4J_DATABASE

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create MESH structured nodes on neo4j from NetworkNodes'

    def add_node(
        self,
        concept_child,
        uniqueID_child,
        concept_parent,
        uniqueID_parent
    ):
        try:
            child=MESH(
                concept_en=concept_child,
                unique_ID=uniqueID_child
            ).save()
        except Exception as e:
            child=MESH.nodes.get(
                concept_en=concept_child,
                unique_ID=uniqueID_child
            )
        try:
            parent=MESH(
                concept_en=concept_parent,
                unique_ID=uniqueID_parent
            ).save()
        except Exception as e:
            parent=MESH.nodes.get(
                concept_en=concept_parent,
                unique_ID=uniqueID_parent
            )
        child.is_a.connect(parent)


    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        pass        

    def handle(self, *args, **options):
        sets = NodeSet.objects.filter(
            name__in=["class", "occupation", "medical_specialty"]
        )
        nodes_qs = NetworkNode.objects.filter(
            node_set__in=sets
        )
        self.stdout.write(
            self.style.WARNING(
                f'{nodes_qs}'
            )
        )
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            driver.verify_connectivity()
            for node in nodes_qs:
                self.warn(f'{node=}');
                ancestors = node.ancestors(max_depth=1)
                for ancestor in ancestors:
                    self.warn(f'{ancestor=}');
                    concept_child = node.mesh.en
                    uniqueID_child = node.mesh.uid
                    concept_parent = ancestor.mesh.en
                    uniqueID_parent = ancestor.mesh.uid
                    self.warn(
                        f'\n{concept_child=}\n'
                        f'{uniqueID_child=}\n'
                        f'{concept_parent=}\n'
                        f'{uniqueID_parent=}\n'
                    )
                    self.add_node(
                        concept_child,
                        uniqueID_child,
                        concept_parent,
                        uniqueID_parent
                    )