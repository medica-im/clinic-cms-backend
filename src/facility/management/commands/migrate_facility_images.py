"""
Move facility pictures out of addressbook.Contact and into facility.PlaceImage.

A handful of facilities were given a picture through Contact.profile_image,
the field meant for the avatar of a natural or legal person. A building is
neither, and Contact's thumbnails are square, so those pictures were cropped
to 1:1 and lost the facade that makes a place recognizable.

The original upload is untouched on disk, so this copies that file — never a
thumbnail — into PlaceImage, where the 16:9 aliases apply.

    python manage.py migrate_facility_images              # preview
    python manage.py migrate_facility_images --apply
    python manage.py migrate_facility_images --apply --delete-source

The source rows are kept unless --delete-source is passed, so a first run is
reversible. Re-running is safe: facilities that already have a PlaceImage are
skipped.
"""
import logging

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from neomodel import db

from addressbook.models import Contact
from facility.models import PlaceImage

logger = logging.getLogger(__name__)

# Pictures whose file name says "logo": a logo cropped to 16:9 looks wrong, so
# these are reported for a human to re-crop rather than silently converted.
LOGO_HINTS = ("logo",)


class Command(BaseCommand):
    help = "Copy facility pictures from Contact.profile_image to PlaceImage"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write; without it the command only reports.",
        )
        parser.add_argument(
            "--delete-source",
            action="store_true",
            help="Clear Contact.profile_image once copied (implies --apply).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"] or options["delete_source"]
        delete_source = options["delete_source"]

        facility_uids = self._facility_uids()
        self.stdout.write(f"Facility nodes in the graph: {len(facility_uids)}")

        candidates = [
            c
            for c in Contact.objects.exclude(profile_image="").exclude(profile_image=None)
            if c.neomodel_uid and self._normalize(c.neomodel_uid) in facility_uids
        ]
        self.stdout.write(f"Facility pictures held on Contact: {len(candidates)}")

        migrated = skipped = failed = 0
        review = []
        deleted = []

        for contact in candidates:
            uid = contact.neomodel_uid
            name = contact.profile_image.name

            if PlaceImage.objects.filter(neomodel_uid=uid).exists():
                # Already copied over. The source is still here, so this is
                # exactly the case --delete-source exists for: a first run
                # copies, you look at the result, a second run clears the
                # originals. Skipping outright would make the flag unusable
                # after the copy it is meant to follow.
                if delete_source:
                    try:
                        contact.profile_image.delete(save=True)
                        deleted.append((uid, name))
                        self.stdout.write(self.style.SUCCESS(f"  freed  {uid}  {name}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"  fail   {uid}  {name}: {e}"))
                        failed += 1
                else:
                    self.stdout.write(f"  skip   {uid}  {name} (already migrated)")
                    skipped += 1
                continue

            if any(hint in name.lower() for hint in LOGO_HINTS):
                review.append((uid, name))

            if not apply_changes:
                self.stdout.write(f"  would  {uid}  {name}")
                migrated += 1
                continue

            try:
                # Read the original, not a rendition: thumbnails are already
                # cropped square and would bake that loss in permanently.
                with contact.profile_image.open("rb") as fh:
                    payload = fh.read()

                place = PlaceImage(neomodel_uid=uid)
                place.image.save(name.split("/")[-1], ContentFile(payload), save=True)

                if delete_source:
                    contact.profile_image.delete(save=True)
                    deleted.append((uid, name))

                self.stdout.write(self.style.SUCCESS(f"  moved  {uid}  {name}"))
                migrated += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  fail   {uid}  {name}: {e}"))
                failed += 1

        verb = "would migrate" if not apply_changes else "migrated"
        self.stdout.write("")
        summary = f"{verb}: {migrated}   skipped: {skipped}   failed: {failed}"
        if delete_source:
            summary += f"   sources deleted: {len(deleted)}"
        self.stdout.write(summary)

        # Named one by one, not just counted: this is the step that cannot be
        # undone, so the record of what it removed has to be readable.
        if deleted:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("Removed from Contact.profile_image (not recoverable):")
            )
            for uid, name in deleted:
                self.stdout.write(f"  {uid}  {name}")

        if review:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "These look like logos rather than photographs of a place, "
                    "and are worth re-cropping by hand at 16:9:"
                )
            )
            for uid, name in review:
                self.stdout.write(f"  {uid}  {name}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write("Dry run — pass --apply to write.")
        elif not delete_source:
            self.stdout.write("")
            self.stdout.write(
                "Source pictures left on Contact. Re-run with --delete-source "
                "once the result looks right."
            )

    def _facility_uids(self) -> set[str]:
        rows, _ = db.cypher_query("MATCH (f:Facility) RETURN f.uid")
        return {self._normalize(r[0]) for r in rows if r[0]}

    @staticmethod
    def _normalize(uid) -> str:
        """Graph uids and Django UUIDs differ only by their dashes."""
        return str(uid).replace("-", "")
