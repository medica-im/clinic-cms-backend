"""Register the other deployments of this app, for the entry clone tool.

The peers are the images.yml entries in the frontend repo — the source of truth
for what is deployed and where — plus the dev hosts. They are listed here rather
than discovered because a peer is a deliberate trust decision: adding a row says
"a superuser may pull entries from that server", and that should be a diff
somebody reviewed, not whatever answered a probe.

Direction matters, and the two flags are not symmetric:

    outbound  we may read FROM that instance
    inbound   that instance may read FROM us

Production is seeded outbound-only. Cloning normally runs production → staging →
dev, and a production server has no business pulling from a development box; a
compromised dev instance should not be able to present itself as a peer that
production will answer. Flip `inbound` in the admin if a genuine case appears.

The instance running this command is skipped: a peer list that offers you
yourself is a confusing way to discover that cloning an entry onto its own
instance does nothing.

    python manage.py seed_peer_instances            # show what would change
    python manage.py seed_peer_instances --write
"""
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from directory.models import PeerInstance

# (name, display_name, origin, outbound, inbound)
PEERS = [
    # Production: readable, never a reader.
    ("santelyon3-prod", "Santé Lyon 3 (production)",
     "https://santelyon3.fr", True, False),
    ("sante-gadagne-prod", "Santé Gadagne (production)",
     "https://sante-gadagne.fr", True, False),
    ("annuaire-medica-prod", "Annuaire Médica (production)",
     "https://annuaire.medica.im", True, False),
    ("cptsopalesud-prod", "CPTS Opale Sud (production)",
     "https://annuaire.cptsopalesud.fr", True, False),
    ("ipa-medica-prod", "IPA Médica (production)",
     "https://ipa.medica.im", True, False),

    # Staging: both directions, it is a rehearsal of production.
    ("santelyon3-staging", "Santé Lyon 3 (staging)",
     "https://staging.santelyon3.fr", True, True),
    ("sante-gadagne-staging", "Santé Gadagne (staging)",
     "https://staging.sante-gadagne.fr", True, True),
    ("annuaire-medica-staging", "Annuaire Médica (staging)",
     "https://staging.annuaire.medica.im", True, True),
    ("ipa-medica-staging", "IPA Médica (staging)",
     "https://staging.ipa.medica.im", True, True),

    # Development: both directions.
    ("santelyon3-dev", "Santé Lyon 3 (dev)",
     "https://dev.santelyon3.fr", True, True),
    ("sante-gadagne-dev", "Santé Gadagne (dev)",
     "https://dev.sante-gadagne.fr", True, True),
    ("annuaire-medica-dev", "Annuaire Médica (dev)",
     "https://dev.annuaire.medica.im", True, True),
]


class Command(BaseCommand):
    help = "Register the peer deployments the entry clone tool may use."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write", action="store_true",
            help="Apply the changes. Without it, only report them.",
        )

    def handle(self, *args, **options):
        write = options["write"]
        # Every hostname this deployment answers on, so it does not offer
        # itself as a peer.
        mine = {s.domain.lower() for s in Site.objects.all()}

        created = updated = skipped = 0
        for name, display, origin, outbound, inbound in PEERS:
            host = origin.split("//", 1)[-1].rstrip("/").lower()
            if host in mine:
                self.stdout.write(f"  self     {display} ({origin})")
                skipped += 1
                continue

            existing = PeerInstance.objects.filter(name=name).first()
            if existing:
                changes = [
                    f"{f}: {getattr(existing, f)!r} -> {v!r}"
                    for f, v in (("display_name", display), ("origin", origin),
                                 ("outbound", outbound), ("inbound", inbound))
                    if getattr(existing, f) != v
                ]
                if not changes:
                    continue
                self.stdout.write(f"  update   {display}: {', '.join(changes)}")
                if write:
                    existing.display_name = display
                    existing.origin = origin
                    existing.outbound = outbound
                    existing.inbound = inbound
                    existing.full_clean()
                    existing.save()
                updated += 1
                continue

            self.stdout.write(
                f"  create   {display} ({origin}) "
                f"outbound={outbound} inbound={inbound}"
            )
            if write:
                peer = PeerInstance(
                    name=name, display_name=display, origin=origin,
                    active=True, outbound=outbound, inbound=inbound,
                )
                peer.full_clean()
                peer.save()
            created += 1

        verb = "wrote" if write else "would write"
        self.stdout.write(self.style.SUCCESS(
            f"{verb}: {created} created, {updated} updated, {skipped} skipped as self"
        ))
        if not write:
            self.stdout.write("Nothing changed. Re-run with --write to apply.")
