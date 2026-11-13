"""Import a directory's entries from a spec (see directory/importer.py for its shape).

Run it in the fastapi container:

    python manage.py import_directory_entries /tmp/import.json --creator-directory santelyon3 \\
        --changed-by jerome@medecinelibre.com [--only row-5,row-6] [--dry-run]

--dry-run lists what does not resolve and what would be imported, and writes nothing.
"""
import asyncio
import json

from django.core.management.base import BaseCommand, CommandError

from api.utils import clear_cache
from directory.importer import selected, import_spec, preflight
from accounts.models import User
from directory.models import Directory


class Command(BaseCommand):
    help = "Import a directory's porteurs and entries from a JSON spec"

    def add_arguments(self, parser):
        parser.add_argument("spec")
        parser.add_argument("--creator-directory", required=True,
                            help="creator_directory of the effectors, as the site's other effectors have it")
        parser.add_argument("--changed-by", required=True,
                            help="email of the existing user the imported descriptions are written by")
        parser.add_argument("--only", help="comma-separated entry keys; their porteurs come along")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        with open(options["spec"], encoding="utf-8") as f:
            spec = json.load(f)
        only = set(options["only"].split(",")) if options["only"] else None
        asyncio.run(self.run(spec, only, options))

    async def run(self, spec, only, options):
        problems = await preflight(spec, only)
        porteurs, entries = selected(spec, only)
        self.stdout.write(f"{len(porteurs)} porteurs, {len(entries)} entries")
        for item in porteurs + entries:
            self.stdout.write(f"  {item['key']}: {item.get('existing') or item.get('name')}")
        for problem in problems:
            self.stdout.write(self.style.ERROR(f"problem: {problem}"))
        if options["dry_run"]:
            return
        if problems:
            raise CommandError(f"{len(problems)} problem(s): nothing written")
        author = await User.objects.filter(email=options["changed_by"]).afirst()
        if author is None:
            raise CommandError(f"no user {options['changed_by']}")
        report = await import_spec(spec, creator_directory=options["creator_directory"], only=only,
                                   changed_by=author)
        directory = await Directory.objects.filter(name=spec["directory"]).select_related("site").afirst()
        for endpoint in ("v2:entries", "v2:effector-type-labels", "v1:facilities", "v2:public/facilities"):
            await clear_cache(endpoint, site=directory.site)
        self.stdout.write(self.style.SUCCESS(f"created {dict(report.created)}, reused {dict(report.reused)}"))
