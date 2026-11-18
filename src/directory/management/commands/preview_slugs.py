import asyncio
import random
from django.core.management.base import BaseCommand
from neomodel import adb
from directory.models.agraph import (
    Entry,
    Effector,
    Facility,
    EffectorType,
)
from directory.slug import generate_entry_slugs

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Preview generated slug candidates for an Entry (by uid) or for random Entries (with --count)"

    def add_arguments(self, parser):
        parser.add_argument(
            "uid",
            nargs="?",
            type=str,
            help="UID of an Entry node",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=1,
            help="Number of random Entries to generate slugs for (used when no uid is given)",
        )

    def handle(self, *args, **options):
        uid = options["uid"]
        count = options["count"]
        asyncio.run(self._run(uid, count))

    async def _run(self, uid: str | None, count: int):
        if uid:
            await self._preview_entry(uid)
        else:
            entries = await self._get_random_entries(count)
            if not entries:
                self.stdout.write(self.style.ERROR("No entries found in the database."))
                return
            for i, entry in enumerate(entries):
                if i > 0:
                    self.stdout.write("")
                await self._preview_entry(entry.uid)

    async def _get_random_entries(self, count: int) -> list:
        results, _ = await adb.cypher_query(
            "MATCH (e:Entry) RETURN e.uid",
        )
        if not results:
            return []
        all_uids = [row[0] for row in results]
        selected = random.sample(all_uids, min(count, len(all_uids)))
        entries = []
        for uid in selected:
            entry = await Entry.nodes.get(uid=uid)
            entries.append(entry)
        return entries

    async def _preview_entry(self, uid: str):
        try:
            entry = await Entry.nodes.get(uid=uid)
        except Entry.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Entry {uid} not found."))
            return

        effectors = await entry.effector.all()
        if not effectors:
            self.stdout.write(self.style.WARNING(f"Entry {uid}: no effector linked."))
            return
        effector = effectors[0]

        facilities = await entry.facility.all()
        if not facilities:
            self.stdout.write(self.style.WARNING(f"Entry {uid}: no facility linked."))
            return
        facility = facilities[0]

        effector_types = await entry.effector_type.all()
        if not effector_types:
            self.stdout.write(self.style.WARNING(f"Entry {uid}: no effector_type linked."))
            return
        effector_type = effector_types[0]

        self.stdout.write(self.style.HTTP_INFO(
            f"--- Entry {uid} ---"
        ))
        self.stdout.write(
            f"  Effector:      {effector.name_fr} (gender={effector.gender})"
        )
        self.stdout.write(
            f"  EffectorType:  {effector_type.name_fr} / {effector_type.label_fr}"
        )
        self.stdout.write(
            f"  Facility zip:  {facility.zip}  street: {facility.street}"
        )
        communes = await facility.commune.all()
        commune_name = communes[0].name_fr if communes else "(none)"
        self.stdout.write(
            f"  Commune:       {commune_name}"
        )
        current_slug = entry.slug
        self.stdout.write(
            f"  Current slug:  {current_slug or '(none)'}"
        )

        slugs = await generate_entry_slugs(effector, facility, effector_type)

        self.stdout.write(self.style.SUCCESS(
            f"  Generated {len(slugs)} slug candidates:"
        ))
        for j, slug in enumerate(slugs, 1):
            self.stdout.write(f"    {j:2d}. {slug}")
