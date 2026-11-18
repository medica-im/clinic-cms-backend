from django.utils.text import slugify

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from workforce.models import NetworkEdge, NodeSet, NetworkNode
from facility.models import Organization
from django.db import DatabaseError, IntegrityError
from directory.models import MESH, HCW

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
        label_en,
        label_fr,
        concept_en,
        concept_fr,
        unique_ID,
    ):
        node=None
        created=False
        try:
            node=HCW(
                label_en=label_en,
                label_fr=label_fr,
                concept_en=concept_en,
                concept_fr=concept_fr,
                unique_ID=unique_ID
            ).save()
            created=True
        except Exception as e:
            #logger.error(e)
            node=HCW.nodes.get(
                unique_ID=unique_ID
            )
        if node and isinstance(node, HCW):
            logger.debug(f'{"new" if created else ""} node: {node=}')


    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def add_arguments(self, parser):
        pass        

    def handle(self, *args, **options):
        mesh_nodes = MESH.nodes.all()
        self.stdout.write(
            self.style.WARNING(
                f'{mesh_nodes=}\n'
                f'count: {len(mesh_nodes)}'
            )
        )
        for node in mesh_nodes:
            self.warn(f'{node=}');
            self.add_node(
                    node.label_en,
                    node.label_fr,
                    node.concept_en,
                    node.concept_fr,
                    node.unique_ID,
                )
        for node in mesh_nodes:
            self.warn(f'{node=}');
            try:
                child_unique_ID=node.unique_ID
                parent_unique_ID=node.is_a[0].unique_ID
            except:
                continue
            child_node=HCW.nodes.get(unique_ID=child_unique_ID)
            logger.debug(f'{child_node=}')
            parent_node=HCW.nodes.get(unique_ID=parent_unique_ID)
            logger.debug(f'{parent_node=}')
            child_node.hcw.connect(parent_node)
                
        for node in mesh_nodes:
            try:
                needs=node.need.all()
                from_unique_ID=node.unique_ID
            except:
                continue
            from_node=HCW.nodes.get(unique_ID=from_unique_ID)
            for need in needs:
                from_node.need.connect(need)

        for node in mesh_nodes:
            try:
                situations=node.situation.all()
                from_unique_ID=node.unique_ID
            except:
                continue
            from_node=HCW.nodes.get(unique_ID=from_unique_ID)
            for situation in situations:
                from_node.situation.connect(situation)

        hcw_nodes = HCW.nodes.all()
        self.stdout.write(
            self.style.WARNING(
                f'{hcw_nodes=}\n'
                f'count: {len(hcw_nodes)}'
            )
        )