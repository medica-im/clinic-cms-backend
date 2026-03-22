import asyncio
from django.core.management.base import BaseCommand
from neomodel import adb
from directory.models.agraph import (
    Entry,
)
from directory.slug import generate_entry_slugs

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Assign slugs to Entry nodes that don't have one yet"

    def add_arguments(self, parser):
        parser.add_argument(
            "uid",
            nargs="?",
            type=str,
            help="UID of a specific Entry node to assign a slug to",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be done without actually assigning slugs",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        uid = options["uid"]
        asyncio.run(self._run(dry_run, uid))

    async def _run(self, dry_run: bool, uid: str | None = None):
        if uid:
            await self._run_single(uid, dry_run)
            return

        # Stats before
        total, with_slug, without_slug = await self._get_stats()
        self.stdout.write(self.style.HTTP_INFO("=== Before ==="))
        self._print_stats(total, with_slug, without_slug)

        if without_slug == 0:
            self.stdout.write(self.style.SUCCESS("All entries already have slugs."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: no slugs will be assigned.\n"))

        # Get all entries without slugs
        results, _ = await adb.cypher_query(
            "MATCH (e:Entry) WHERE e.slug IS NULL OR e.slug = '' RETURN e.uid",
        )
        uids = [row[0] for row in results]

        assigned = 0
        skipped = 0
        failed = 0

        for uid in uids:
            result = await self._assign_slug(uid, dry_run)
            if result == "assigned":
                assigned += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1

        # Stats after
        self.stdout.write("")
        if not dry_run:
            total, with_slug, without_slug = await self._get_stats()
            self.stdout.write(self.style.HTTP_INFO("=== After ==="))
            self._print_stats(total, with_slug, without_slug)

        self.stdout.write(self.style.HTTP_INFO("\n=== Summary ==="))
        prefix = "(dry-run) " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"  {prefix}Assigned: {assigned}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"  {prefix}Skipped (missing data): {skipped}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"  {prefix}Failed (no available slug): {failed}"))

    async def _run_single(self, uid: str, dry_run: bool):
        """Assign a slug to a specific entry by uid."""
        try:
            entry = await Entry.nodes.get(uid=uid)
        except Entry.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Entry {uid} not found."))
            return

        current_slug = entry.slug
        if current_slug:
            self.stdout.write(self.style.WARNING(
                f"Entry {uid} already has slug '{current_slug}'. Overwriting."
            ))

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: no slug will be assigned.\n"))

        result = await self._assign_slug(uid, dry_run)
        if result == "assigned" and not dry_run:
            self.stdout.write(self.style.SUCCESS("Done."))
        elif result == "skipped":
            self.stdout.write(self.style.WARNING("Entry skipped due to missing data."))
        elif result == "failed":
            self.stdout.write(self.style.ERROR("Failed to assign a slug."))

    async def _get_stats(self) -> tuple[int, int, int]:
        results, _ = await adb.cypher_query(
            "MATCH (e:Entry) "
            "RETURN count(e), "
            "sum(CASE WHEN e.slug IS NOT NULL AND e.slug <> '' THEN 1 ELSE 0 END), "
            "sum(CASE WHEN e.slug IS NULL OR e.slug = '' THEN 1 ELSE 0 END)",
        )
        row = results[0] if results else [0, 0, 0]
        return int(row[0]), int(row[1]), int(row[2])

    def _print_stats(self, total: int, with_slug: int, without_slug: int):
        self.stdout.write(f"  Total entries:   {total}")
        self.stdout.write(f"  With slug:       {with_slug}")
        self.stdout.write(f"  Without slug:    {without_slug}")

    async def _assign_slug(self, uid: str, dry_run: bool) -> str:
        """Try to assign a slug to an entry. Returns 'assigned', 'skipped', or 'failed'."""
        try:
            entry = await Entry.nodes.get(uid=uid)
        except Entry.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"  Entry {uid}: not found (race condition?)"))
            return "failed"

        effectors = await entry.effector.all()
        if not effectors:
            self.stdout.write(self.style.WARNING(f"  Entry {uid}: no effector linked, skipping."))
            return "skipped"
        effector = effectors[0]

        facilities = await entry.facility.all()
        if not facilities:
            self.stdout.write(self.style.WARNING(f"  Entry {uid}: no facility linked, skipping."))
            return "skipped"
        facility = facilities[0]

        effector_types = await entry.effector_type.all()
        if not effector_types:
            self.stdout.write(self.style.WARNING(f"  Entry {uid}: no effector_type linked, skipping."))
            return "skipped"
        effector_type = effector_types[0]

        slugs = await generate_entry_slugs(effector, facility, effector_type)
        if not slugs:
            self.stdout.write(self.style.ERROR(f"  Entry {uid}: no slug candidates generated."))
            return "failed"

        # Try each slug candidate until one works
        for slug in slugs:
            try:
                results, _ = await adb.cypher_query(
                    "MATCH (e:Entry {uid: $uid}) "
                    "SET e.slug = $slug "
                    "RETURN e.slug",
                    {"uid": uid, "slug": slug if not dry_run else None},
                )
                if dry_run:
                    self.stdout.write(f"  Entry {uid}: would assign '{slug}'")
                    return "assigned"
                self.stdout.write(self.style.SUCCESS(f"  Entry {uid}: assigned '{slug}'"))
                return "assigned"
            except Exception as e:
                if "already exists" in str(e).lower() or "constraint" in str(e).lower():
                    logger.debug(f"Entry {uid}: slug '{slug}' taken, trying next...")
                    continue
                self.stdout.write(self.style.ERROR(
                    f"  Entry {uid}: unexpected error setting slug '{slug}': {e}"
                ))
                return "failed"

        self.stdout.write(self.style.ERROR(
            f"  Entry {uid}: all {len(slugs)} slug candidates are taken."
        ))
        return "failed"
