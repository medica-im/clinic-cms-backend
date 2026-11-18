import asyncio
from django.core.management.base import BaseCommand
from neomodel import adb

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Generate Cypher queries to add synonyms_fr from this database's "
        "EffectorType nodes to another database (matched by name_fr)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output file path for the Cypher script. Prints to stdout if not set.",
        )

    def handle(self, *args, **options):
        output = options["output"]
        asyncio.run(self._run(output))

    async def _run(self, output: str | None):
        results, _ = await adb.cypher_query(
            "MATCH (et:EffectorType) "
            "WHERE et.synonyms_fr IS NOT NULL AND size(et.synonyms_fr) > 0 "
            "RETURN et.name_fr, et.synonyms_fr "
            "ORDER BY et.name_fr",
        )

        if not results:
            self.stdout.write(self.style.WARNING("No EffectorType nodes with synonyms_fr found."))
            return

        lines = []
        for name_fr, synonyms_fr in results:
            if not name_fr or not synonyms_fr:
                continue
            escaped_name = name_fr.replace("\\", "\\\\").replace("'", "\\'")
            syn_parts = []
            for s in synonyms_fr:
                syn_parts.append("'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'")
            syn_literal = "[" + ", ".join(syn_parts) + "]"
            stmt = (
                f"MATCH (et:EffectorType {{name_fr: '{escaped_name}'}}) "
                f"SET et.synonyms_fr = apoc.coll.toSet(coalesce(et.synonyms_fr, []) + {syn_literal});"
            )
            lines.append(stmt)

        script = "\n".join(lines) + "\n"

        if output:
            with open(output, "w") as f:
                f.write(script)
            self.stdout.write(self.style.SUCCESS(
                f"Written {len(lines)} Cypher statements to {output}"
            ))
        else:
            self.stdout.write(script)

        self.stdout.write(self.style.SUCCESS(f"{len(lines)} EffectorType nodes with synonyms_fr."))
