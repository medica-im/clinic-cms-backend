import logging
from uuid import UUID

from django.core.management.base import BaseCommand
from neomodel import db

from access.active_access import active_key
from access.roles import ROLES
from access.neomodels import Access, User
from directory.models.graph import Entry

logger = logging.getLogger(__name__)


def normalize_uid(value: str) -> str:
    """Accept a UUID with or without dashes and return the hex (no dashes) form."""
    try:
        return UUID(value).hex
    except ValueError:
        return value


class Command(BaseCommand):
    help = "Create a neo4j Access node linking a User to an Entry with a given role"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            required=True,
            help="UID of the neo4j User node",
        )
        parser.add_argument(
            "--entry",
            required=True,
            help="UID of the neo4j Entry node",
        )
        parser.add_argument(
            "--role",
            required=True,
            choices=list(ROLES),
            help="Role for the Access node",
        )
        parser.add_argument(
            "--creator",
            required=True,
            help="UID of the neo4j User who is creating this Access",
        )

    def handle(self, *args, **options):
        user_uid = normalize_uid(options["user"])
        entry_uid = normalize_uid(options["entry"])
        created_by_uid = normalize_uid(options["creator"])
        role = options["role"]

        # Fetch User node
        try:
            user = User.nodes.get(uid=user_uid)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User with uid={user_uid} not found"))
            return

        # Fetch creator User node
        try:
            creator = User.nodes.get(uid=created_by_uid)
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"Creator User with uid={created_by_uid} not found")
            )
            return

        # Fetch Entry node
        try:
            entry = Entry.nodes.get(uid=entry_uid)
        except Entry.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"Entry with uid={entry_uid} not found")
            )
            return

        query = (
            "MATCH (u:User {uid: $user_uid})-[:HAS_ACCESS]->(a:Access {active: true})"
            "-[:ACCESS_TO]->(e:Entry {uid: $entry_uid}) "
            "RETURN a.role"
        )
        results, _ = db.cypher_query(
            query, {"user_uid": user_uid, "entry_uid": entry_uid}
        )
        if results:
            self.stdout.write(
                self.style.WARNING(
                    f"user={user_uid} already holds role={results[0][0]} on "
                    f"entry={entry_uid}; change it from the user page instead"
                )
            )
            return

        access = Access(
            role=role, activeKey=active_key(user_uid, entry_uid)
        ).save()
        user.access.connect(access)
        access.entry.connect(entry)
        access.createdBy.connect(creator)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created Access (uid={access.uid}, role={role}) "
                f"for user={user_uid} on entry={entry_uid}"
            )
        )
