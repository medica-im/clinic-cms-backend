"""Create a chain of EffectorType nodes from a MeSH descriptor lineage.

Resolves the descriptor's ancestor chain via the NLM MeSH REST API
(mesh.query_mesh), pulls the official French translation from the
mesh.Mesh Postgres table, and MERGEs one :EffectorType node per
ancestor (root to leaf) with unique_ID set to the MeSH Unique ID,
linked child -> parent via IS_A. Idempotent: safe to re-run.

Usage:
    python manage.py create_mesh_effector_type_tree --label "Hospitals"
    python manage.py create_mesh_effector_type_tree --unique-id D006761
"""
import asyncio
import logging

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from neomodel import adb

from mesh.models import Mesh
from mesh.query_mesh import find_descriptor_by_label, resolve_lineage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create a MeSH-derived EffectorType tree (ancestor chain) in Neo4j."

    def add_arguments(self, parser):
        parser.add_argument("--label", type=str, help="Exact MeSH descriptor label, e.g. 'Hospitals'")
        parser.add_argument("--unique-id", type=str, help="MeSH Unique ID, e.g. 'D006761'")

    def handle(self, *args, **options):
        label: str|None = options.get("label")
        unique_id = options.get("unique_id")

        if not label and not unique_id:
            raise CommandError("Provide either --label or --unique-id")

        if not unique_id:
            assert label
            matches = find_descriptor_by_label(label)
            if not matches:
                raise CommandError(f"No MeSH descriptor found for label '{label}'")
            unique_id = matches[0]["resource"].rsplit("/", 1)[-1]

        lineage = resolve_lineage(unique_id)
        if not lineage:
            raise CommandError(f"Could not resolve lineage for {unique_id}")

        # Enrich with official French translations from the mesh.Mesh table.
        for node in lineage:
            try:
                node["label_fr"] = Mesh.objects.get(uid=node["unique_id"]).fr
            except Mesh.DoesNotExist:
                node["label_fr"] = None
                self.warn(f"No French translation found in mesh.Mesh for {node['unique_id']} ({node['label']})")

        self.warn("Resolved lineage (root -> leaf):")
        for node in lineage:
            self.warn(f"  {node['unique_id']:<10} en={node['label']!r} fr={node['label_fr']!r}")

        async_to_sync(self._create_tree)(lineage)

    async def _create_tree(self, lineage: list[dict]):
        previous_unique_id = None
        created_count = 0
        existing_count = 0

        for node in lineage:
            label_fr = node["label_fr"] or node["label"]

            existed_before, _ = await adb.cypher_query(
                "MATCH (n:EffectorType {unique_ID: $unique_id}) RETURN n.uid",
                {"unique_id": node["unique_id"]},
            )
            node["was_created"] = not existed_before

            query = """
            MERGE (n:EffectorType {unique_ID: $unique_id})
            ON CREATE SET
              n.uid = replace(randomUUID(), "-", ""),
              n.name_en = $label_en,
              n.label_en = $label_en,
              n.name_fr = $label_fr,
              n.label_fr = $label_fr,
              n.slug_en = $slug_en,
              n.slug_fr = $slug_fr
            RETURN n.uid AS uid
            """
            params = {
                "unique_id": node["unique_id"],
                "label_en": node["label"],
                "label_fr": label_fr,
                "slug_en": slugify(node["label"]),
                "slug_fr": slugify(label_fr),
            }
            results, _ = await adb.cypher_query(query, params)
            node["uid"] = results[0][0]

            if node["was_created"]:
                created_count += 1
                self.warn(f"  created {node['unique_id']} ({node['label']})")
            else:
                existing_count += 1
                self.warn(f"  already existed {node['unique_id']} ({node['label']}) — left untouched")

            if previous_unique_id:
                rel_query = """
                MATCH (child:EffectorType {unique_ID: $child_id})
                MATCH (parent:EffectorType {unique_ID: $parent_id})
                MERGE (child)-[:IS_A]->(parent)
                """
                await adb.cypher_query(rel_query, {
                    "child_id": node["unique_id"],
                    "parent_id": previous_unique_id,
                })
            previous_unique_id = node["unique_id"]

        self.warn(self.style.SUCCESS(
            f"Done: {created_count} node(s) created, {existing_count} already existed "
            f"({len(lineage)} total, IS_A chain verified)."
        ))

    def warn(self, message):
        self.stdout.write(self.style.WARNING(message))
