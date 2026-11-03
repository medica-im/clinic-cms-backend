"""Give every facility a slug of its own.

A facility is addressed by its slug (/sites/{slug}, and
/api/v2/public/facilities/{slug}, which returns rows[0]). Two facilities sharing
a slug make one of them unreachable, and a facility with none has only its uid.

Two repairs, in this order:

  merge   facilities with one slug, one name and one address are one place
          recorded several times: their entries and owners move to the one with
          the most active entries, and the duplicates are deleted. One with
          contacts or images, or whose entries would collide with the kept
          one's, is only reported, for a person to merge by hand.
  rename  different places sharing a slug, and facilities with none, get the slug
          the creation form would now generate (directory/facility_slug.py).
          A new slug is free only when no facility anywhere holds it.

Dry run by default. Nothing is written without --write. A renamed facility's old
address stops working; facilities have no redirects.
"""
from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand
from neomodel import adb

from directory.facility_slug import merge_facility, plan_facility_merges, plan_slug_repairs

RENAME = "MATCH (f:Facility {uid: $uid}) SET f.slug = $slug"


class Command(BaseCommand):
    help = "Merge duplicate facilities, then give every facility its own slug."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Apply the plan. Without it nothing is written.")

    async def run(self, write: bool):
        merges = await plan_facility_merges()
        renames = await plan_slug_repairs()
        for m in merges:
            if m.blocked:
                self.stdout.write(self.style.WARNING(
                    f"BLOCKED  {m.drop_uid}  {m.name or ''}  duplicate of {m.keep_uid}: {m.blocked}"
                ))
                continue
            self.stdout.write(f"merge    {m.drop_uid}  {m.name or ''}  into {m.keep_uid}  ({m.entries} entries)")
            if write:
                await merge_facility(m.keep_uid, m.drop_uid)
        for r in renames:
            self.stdout.write(f"rename   {r.uid}  {r.name or ''}  {r.old or '(none)'} -> {r.new}  [{r.reason}]")
            if write:
                await adb.cypher_query(RENAME, {"uid": r.uid, "slug": r.new})
        return merges, renames

    def handle(self, *args, **options):
        # One coroutine, so one event loop: the async Neo4j connection belongs to
        # the loop that opened it.
        merges, renames = async_to_sync(self.run)(options["write"])
        write = options["write"]
        blocked = sum(1 for m in merges if m.blocked)
        merged = len(merges) - blocked

        self.stdout.write("")
        if not (merges or renames):
            self.stdout.write(self.style.SUCCESS("every facility already has a slug of its own"))
        elif write:
            self.stdout.write(self.style.SUCCESS(f"merged {merged}, renamed {len(renames)}, left {blocked}"))
            self.stdout.write(self.style.WARNING(
                "the facility caches still hold the old slugs; clear v1:facilities, "
                "v2:public/facilities and v2:entries"
            ))
        else:
            self.stdout.write(
                f"dry run: {merged} would be merged, {len(renames)} renamed, {blocked} left for a person. "
                "Re-run with --write to apply."
            )
