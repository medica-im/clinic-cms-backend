"""The APOC triggers that maintain createdAt/updatedAt on every graph node.

A migration rather than a script, for the same reason schema changes are one:
it runs on `manage.py migrate`, which every deploy already does, so a machine
cannot end up with the code that assumes these triggers and not the triggers
themselves.

The two timestamp triggers predate this migration — they were installed by hand
and had been running for as long as anyone could remember. Nothing in a
checkout said so, and a reading of the Python source concluded the opposite:
that nothing wrote createdAt/updatedAt and that the graph had no equivalent of
Django's signals. Both conclusions were wrong, and the only way to doubt them
was to query a live database. Declaring them here is most of the point of this
migration; the third and fourth are new.

apoc.trigger.add is idempotent — it replaces a trigger of the same name — so
re-running this is safe on a database that already has them.
"""
from django.db import migrations


# Every property write carries its own timestamp, so the application never has
# to. `before` phase, so the value lands in the same transaction as the change
# rather than as a second write after it.
CREATE_TIMESTAMP = """
UNWIND $createdNodes AS node
SET node.createdAt = timestamp()
"""

UPDATE_TIMESTAMP = """
UNWIND keys($assignedNodeProperties) as key
UNWIND apoc.trigger.propertiesByKey($assignedNodeProperties, key) as update
WITH update.node as node
SET node.updatedAt = timestamp()
"""

# The gap the two above leave, and the reason this migration adds anything.
#
# A relationship change assigns no node property, so neither trigger fires. An
# entry gaining a tag, joining an organisation, changing owner or moving
# directory looked untouched — and those are edits an owner or administrator
# makes from the entry page, so the administrative table reported them as
# unmodified. Verified rather than assumed: creating a relationship left
# updatedAt byte-identical before and after.
#
# Both endpoints are stamped because either can be the entry. (entry)<-[:TAGS]-
# runs one way and (entry)-[:MEMBER_OF]->(entry) the other; a trigger that
# picked one would miss half the cases.
RELATIONSHIP_CREATED_TIMESTAMP = """
UNWIND $createdRelationships AS rel
WITH [startNode(rel), endNode(rel)] AS nodes
UNWIND nodes AS node
SET node.updatedAt = timestamp()
"""

# `before` is required here, not stylistic: in `after` the relationship is
# already gone and startNode() has nothing to return. Confirmed against a live
# 4.4.48 database — the `after` form silently stamped nothing.
#
# The $deletedNodes guard is not defensive coding, it is required. A DETACH
# DELETE removes the relationship *and* its nodes in one transaction, so
# startNode() names something the trigger cannot load, and the whole
# transaction fails with "Unable to load NODE with id 0" — turning a legitimate
# delete into a 500. Stamping a node that is itself being deleted would be
# pointless anyway.
RELATIONSHIP_DELETED_TIMESTAMP = """
UNWIND $deletedRelationships AS rel
WITH [n IN [startNode(rel), endNode(rel)] WHERE NOT n IN $deletedNodes] AS nodes
UNWIND nodes AS node
SET node.updatedAt = timestamp()
"""

TRIGGERS = {
    "create-timestamp": CREATE_TIMESTAMP,
    "update-insert-timestamp": UPDATE_TIMESTAMP,
    "relationship-created-timestamp": RELATIONSHIP_CREATED_TIMESTAMP,
    "relationship-deleted-timestamp": RELATIONSHIP_DELETED_TIMESTAMP,
}

# The two this migration introduces. Only these are removed on reverse: the
# timestamp pair was here first and other things depend on it, so unapplying
# this migration must not take them away.
ADDED_BY_THIS_MIGRATION = [
    "relationship-created-timestamp",
    "relationship-deleted-timestamp",
]


def install(apps, schema_editor):
    from neomodel import db

    for name, query in TRIGGERS.items():
        db.cypher_query(
            "CALL apoc.trigger.add($name, $query, {phase: 'before'})",
            {"name": name, "query": query.strip()},
        )


def uninstall(apps, schema_editor):
    from neomodel import db

    for name in ADDED_BY_THIS_MIGRATION:
        db.cypher_query("CALL apoc.trigger.remove($name)", {"name": name})


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0027_alter_assetfacility_unique_together_and_more"),
    ]

    operations = [
        # elidable=False: this touches Neo4j, which squashing cannot replay
        # from the Django model state.
        migrations.RunPython(install, uninstall, elidable=False),
    ]
