"""Give each facility of an organization its own slug.

A facility is addressed by its slug — /sites/{slug}, and
/api/v2/public/facilities/{slug}, which returns rows[0]. Two facilities of one
organization sharing a slug make one of them unreachable: the graph answers
with whichever it finds first, every time.

api.serializers.facility.assert_slug_is_free now refuses to create such a pair,
but it cannot repair the ones already in the graph. This does that, by
appending the street to the name — the thing that actually distinguishes two
cabinets infirmiers of the same organization.

Scoped per organization, like the guard: two unrelated organizations are each
entitled to a "cabinet-medical", and only clashes *within* one are a problem.

Dry run by default. Nothing is written without --write.
"""

import re

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from neomodel import db


HOUSE_NUMBER = re.compile(r"^\s*\d+\s*(bis|ter|quater)?\s*,?\s*", re.I)


def street_name(street: str | None) -> str:
    """The street without its house number: '10 Rue Paul Bert' -> 'Rue Paul Bert'.

    The number is what distinguishes two addresses on one street, but it makes
    a poor slug: '10' says nothing to a reader, and the resulting URL reads as
    a house rather than a place. The name alone is enough wherever an
    organization's facilities are on different streets, which is the usual
    case. Where it is not, the number comes back — see full_address below.
    """
    return HOUSE_NUMBER.sub("", street or "").strip()


def full_address(street: str | None) -> str:
    """The street as written, number included.

    The fallback for facilities on the *same* street, where the name alone
    cannot tell them apart: '1 Rue des Arènes' and '2 Rue des Arènes' are
    genuinely different places and the number is the only thing that says so.
    """
    return (street or "").strip()


CLASHES = """
MATCH (f:Facility)-[:PART_OF]->(o)
WHERE f.slug IS NOT NULL
WITH o.uid AS org, f.slug AS slug,
     collect({uid: f.uid, name: f.name, street: f.street}) AS facilities
WHERE size(facilities) > 1
RETURN org, slug, facilities
ORDER BY org, slug
"""

TAKEN = """
MATCH (x:Facility)-[:PART_OF]->(o)
WHERE o.uid = $org AND x.slug = $slug AND x.uid <> $uid
RETURN count(x)
"""

RENAME = "MATCH (f:Facility {uid: $uid}) SET f.slug = $slug"


class Command(BaseCommand):
    help = "Rename facilities that share a slug within one organization."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            help="Apply the renames. Without it nothing is written.",
        )
        parser.add_argument(
            "--slug",
            help="Only touch this slug (e.g. cabinet-infirmier).",
        )

    def handle(self, *args, **options):
        write = options["write"]
        only = options.get("slug")

        # Plain maps rather than resolve_objects: that wraps each node in a
        # list, and only three properties are needed here.
        rows, _ = db.cypher_query(CLASHES)
        planned = 0
        skipped = 0

        for org, slug, facilities in rows:
            if only and slug != only:
                continue

            self.stdout.write(f"\norganization {org}  slug '{slug}'  ×{len(facilities)}")

            # Every one of them is renamed, the bare slug left to nobody: a
            # slug that still answers for one arbitrary facility is the same
            # ambiguity, just quieter.
            #
            # Planned before anything is written, so a set that cannot be told
            # apart by street name leaves the graph untouched rather than
            # half-renamed.
            plan = []
            blocked = False
            for facility in sorted(facilities, key=lambda f: f["uid"]):
                street = street_name(facility["street"])
                if not street:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  BLOCKED {facility['uid']}  no street to name it by"
                        )
                    )
                    blocked = True
                    continue
                plan.append(
                    (
                        facility["uid"],
                        slugify(f"{facility['name'] or slug} {street}"),
                        facility["street"],
                    )
                )

            # Two facilities on the same street need the house number after all:
            # '1 Rue des Arènes' and '2 Rue des Arènes' are different places and
            # the number is the only thing that says so. Applied only to the
            # ones that actually collide, so the readable form is kept wherever
            # it works.
            proposed = [new for _, new, _ in plan]
            clashing = {n for n in proposed if proposed.count(n) > 1}
            if clashing:
                self.stdout.write(
                    f"  same street name ×{len(clashing)}: adding the number"
                )
                plan = [
                    (
                        uid,
                        slugify(f"{slug} {full_address(raw)}") if new in clashing else new,
                        raw,
                    )
                    for uid, new, raw in plan
                ]
                # Identical addresses cannot be told apart by any address at
                # all. That is a data problem, not a naming one.
                proposed = [new for _, new, _ in plan]
                still = {n for n in proposed if proposed.count(n) > 1}
                if still:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  BLOCKED identical addresses: {', '.join(sorted(still))}"
                            " — these are duplicate records, not a naming problem"
                        )
                    )
                    blocked = True

            for uid, new_slug, _ in plan:
                taken, _ = db.cypher_query(
                    TAKEN, {"org": org, "slug": new_slug, "uid": uid}
                )
                if taken and taken[0][0]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  BLOCKED {uid}  '{new_slug}' is already taken"
                        )
                    )
                    blocked = True

            if blocked:
                self.stdout.write(
                    self.style.WARNING("  -> left untouched, nothing written for this slug")
                )
                skipped += len(facilities)
                continue

            for uid, new_slug, _ in plan:
                self.stdout.write(f"  rename {uid}  -> {new_slug}")
                planned += 1
                if write:
                    db.cypher_query(RENAME, {"uid": uid, "slug": new_slug})

        self.stdout.write("")
        if write:
            self.stdout.write(self.style.SUCCESS(f"renamed {planned}, skipped {skipped}"))
            self.stdout.write(
                self.style.WARNING(
                    "the facility caches still hold the old slugs; clear "
                    "v1:facilities, v2:public/facilities and v2:entries"
                )
            )
        else:
            self.stdout.write(
                f"dry run: {planned} would be renamed, {skipped} skipped. "
                "Re-run with --write to apply."
            )
