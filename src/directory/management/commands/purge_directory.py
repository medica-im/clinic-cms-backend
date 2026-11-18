"""Remove a retired directory from Neo4j and Postgres.

What goes is decided by exclusivity, never by the directory alone, because one
person may hold entries in several directories (see the Entry graph model):

* an Entry goes only if no other directory lists it; a shared one just loses
  this directory;
* an Effector, Facility or Appointment goes only if every entry pointing at it
  goes;
* the owner (a non-Entry node behind OWNED_BY, e.g. an Organization) goes only
  if no other directory is owned by it and no surviving entry is a member of
  it, together with its websites that nothing else links to;
* in Postgres: the Contact rows of the deleted entries and effectors, the
  Directory row and, when its site has no other directory, the site with its
  Organization and that Organization's Facility rows (PROTECTed, so first).

Everything runs in one Django transaction with Neo4j last, so a failure in the
graph rolls Postgres back. Tested by tests/api/test_purge_directory.py.
"""
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from neomodel import db

ENTRIES = """
MATCH (d:Directory {name: $name})-[:HAS_ENTRY]->(e:Entry)
WITH e, size([(e)<-[:HAS_ENTRY]-(o:Directory) WHERE o.name <> $name | o]) AS elsewhere
RETURN collect(CASE WHEN elsewhere = 0 THEN e.uid END),
       collect(CASE WHEN elsewhere > 0 THEN e.uid END)
"""

# Nodes every one of whose entries is being deleted. {rel} is one of
# EXCLUSIVE_RELATIONSHIPS, never user input.
EXCLUSIVE = """
MATCH (e:Entry)-[:{rel}]->(n)
WHERE e.uid IN $entries
WITH DISTINCT n
WHERE all(uid IN [(n)<-[:{rel}]-(x:Entry) | x.uid] WHERE uid IN $entries)
RETURN collect(id(n)), collect(n.uid)
"""
EXCLUSIVE_RELATIONSHIPS = {
    "HAS_EFFECTOR": "Effector",
    "HAS_FACILITY": "Facility",
    "HAS_APPOINTMENT": "Appointment",
}

OWNER = """
MATCH (d:Directory {name: $name})-[:OWNED_BY]->(o)
WHERE NOT o:Entry
  AND size([(o)<-[:OWNED_BY]-(x:Directory) WHERE x <> d | x]) = 0
  AND all(uid IN [(o)<-[:MEMBER_OF]-(x:Entry) | x.uid] WHERE uid IN $entries)
OPTIONAL MATCH (o)-[:OFFICIAL_WEBSITE]->(w:Website)
WHERE size([(w)--(y) WHERE y <> o | y]) = 0
RETURN collect(DISTINCT id(o)), collect(DISTINCT id(w))
"""


class Command(BaseCommand):
    help = "Remove a retired directory and what only it uses, from Neo4j and Postgres."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Directory name (Neo4j Directory.name)")
        parser.add_argument("--dry-run", action="store_true", help="Report the counts, delete nothing")

    def handle(self, *args, name, dry_run, **options):
        rows, _ = db.cypher_query("MATCH (d:Directory {name: $name}) RETURN count(d)", {"name": name})
        if rows[0][0] == 0:
            raise CommandError(f'No Neo4j Directory named "{name}"')

        graph = self.plan_graph(name)
        postgres = self.plan_postgres(name, graph)
        self.report(graph, postgres)
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: nothing deleted."))
            return

        with transaction.atomic():
            self.delete_postgres(postgres)
            self.delete_graph(name, graph)
        self.stdout.write(self.style.SUCCESS(f'Directory "{name}" purged.'))

    # --- plan ---------------------------------------------------------------

    def plan_graph(self, name):
        rows, _ = db.cypher_query(ENTRIES, {"name": name})
        own, shared = rows[0] if rows else ([], [])
        plan = {"entries": own, "shared_entries": shared, "node_ids": [], "effector_uids": [], "counts": {}}
        for rel, label in EXCLUSIVE_RELATIONSHIPS.items():
            rows, _ = db.cypher_query(EXCLUSIVE.format(rel=rel), {"entries": own})
            ids, uids = rows[0]
            plan["node_ids"] += ids
            plan["counts"][label] = len(ids)
            if label == "Effector":
                plan["effector_uids"] = [uid for uid in uids if uid]
        rows, _ = db.cypher_query(OWNER, {"name": name, "entries": own})
        owner_ids, website_ids = rows[0] if rows else ([], [])
        plan["node_ids"] += owner_ids + website_ids
        plan["counts"]["Owner"] = len(owner_ids)
        plan["counts"]["Website"] = len(website_ids)
        return plan

    def plan_postgres(self, name, graph):
        from addressbook.models import Contact
        from directory.models import Directory
        from facility.models import Facility, Organization

        contact_uids = [uuid.UUID(uid) for uid in graph["entries"] + graph["effector_uids"]]
        plan = {"contacts": Contact.objects.filter(neomodel_uid__in=contact_uids), "directory": None, "site": None}
        directory = Directory.objects.filter(name=name).select_related("site").first()
        if directory is None:
            return plan
        plan["directory"] = directory
        site = directory.site
        if site and not Directory.objects.filter(site=site).exclude(pk=directory.pk).exists():
            plan["site"] = site
            plan["organizations"] = Organization.objects.filter(site=site)
            plan["facilities"] = Facility.objects.filter(organization__site=site)
        return plan

    def report(self, graph, postgres):
        lines = [
            f"Neo4j Entry: {len(graph['entries'])} deleted, {len(graph['shared_entries'])} kept (listed elsewhere)",
            *(f"Neo4j {label}: {n}" for label, n in graph["counts"].items()),
            f"Postgres Contact: {postgres['contacts'].count()}",
            f"Postgres Directory: {1 if postgres['directory'] else 0}",
        ]
        if postgres["site"]:
            lines += [
                f"Postgres Facility: {postgres['facilities'].count()}",
                f"Postgres Organization: {postgres['organizations'].count()}",
                f"Postgres Site: {postgres['site'].domain}",
            ]
        elif postgres["directory"]:
            lines.append("Postgres Site: kept (it has other directories)")
        for line in lines:
            self.stdout.write(line)

    # --- delete -------------------------------------------------------------

    def delete_postgres(self, plan):
        plan["contacts"].delete()
        if plan["directory"]:
            plan["directory"].delete()
        if plan["site"]:
            plan["facilities"].delete()
            plan["organizations"].delete()
            plan["site"].delete()

    def delete_graph(self, name, plan):
        with db.transaction:
            db.cypher_query("MATCH (n) WHERE id(n) IN $ids DETACH DELETE n", {"ids": plan["node_ids"]})
            db.cypher_query("MATCH (e:Entry) WHERE e.uid IN $uids DETACH DELETE e", {"uids": plan["entries"]})
            db.cypher_query("MATCH (d:Directory {name: $name}) DETACH DELETE d", {"name": name})
