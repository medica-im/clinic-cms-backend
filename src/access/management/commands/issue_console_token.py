from django.core.management.base import BaseCommand, CommandError
from neomodel import db

from access.models import ConsoleToken


def account_sub(email: str) -> str | None:
    """The sub of the account of the User with this email, when there is one."""
    rows, _ = db.cypher_query(
        "MATCH (u:User)-[:HAS_ACCOUNT]->(a:Account) WHERE toLower(u.email) = toLower($email) RETURN a.sub",
        {"email": email},
    )
    return rows[0][0] if len(rows) == 1 else None


class Command(BaseCommand):
    help = "Issue a console token standing for the account of the user with this email; prints it once"

    def add_arguments(self, parser):
        parser.add_argument("--label", required=True, help="What the token is for, e.g. console.medica.im")
        parser.add_argument("--email", required=True, help="Email of the User the console acts as")

    def handle(self, *args, **options):
        sub = account_sub(options["email"])
        if not sub:
            raise CommandError(f"no single account for {options['email']}")
        self.stdout.write(ConsoleToken.issue(label=options["label"], sub=sub))
