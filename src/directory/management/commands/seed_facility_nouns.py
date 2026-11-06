"""Give the existing profession types their place word (facility_noun_fr).

The word names an office in its facility's address ("cabinet-de-kinesitherapie-
rue-paul-bert-lyon"). Only types that have none are written; a word already set
is reported and kept.

Dry run by default. Nothing is written without --write.
"""
from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from directory.facility_nouns import apply_facility_nouns, plan_facility_nouns


class Command(BaseCommand):
    help = "Set facility_noun_fr on the EffectorTypes that have none."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Apply the plan. Without it nothing is written.")

    async def run(self, write: bool):
        plan = await plan_facility_nouns()
        for c in plan.changes:
            self.stdout.write(f"set      {c.name_fr}  ->  {c.new}")
        for k in plan.kept:
            self.stdout.write(self.style.WARNING(f"kept     {k.name_fr}  has {k.old!r}, table says {k.new!r}"))
        for name in plan.missing:
            self.stdout.write(f"missing  {name}  (no such type on this backend)")
        if write:
            await apply_facility_nouns(plan)
        return plan

    def handle(self, *args, **options):
        write = options["write"]
        plan = async_to_sync(self.run)(write)
        self.stdout.write("")
        if write:
            self.stdout.write(self.style.SUCCESS(f"set {len(plan.changes)}, kept {len(plan.kept)}, missing {len(plan.missing)}"))
            self.stdout.write(self.style.WARNING("clear the effector type caches (v2:*) so the words show"))
        else:
            self.stdout.write(
                f"dry run: {len(plan.changes)} would be set, {len(plan.kept)} kept, {len(plan.missing)} missing. "
                "Re-run with --write to apply."
            )
