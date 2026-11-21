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

The definitions live in directory/neo4j_triggers.py. Installing replaces a
trigger of the same name, so re-running this is safe on a database that already
has them.
"""
from django.db import migrations


# The two this migration introduces. Only these are removed on reverse: the
# timestamp pair was here first and other things depend on it, so unapplying
# this migration must not take them away.
ADDED_BY_THIS_MIGRATION = [
    "relationship-created-timestamp",
    "relationship-deleted-timestamp",
]


def install(apps, schema_editor):
    from directory import neo4j_triggers

    neo4j_triggers.install()


def uninstall(apps, schema_editor):
    from directory import neo4j_triggers

    neo4j_triggers.remove(ADDED_BY_THIS_MIGRATION)


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0027_alter_assetfacility_unique_together_and_more"),
    ]

    operations = [
        # elidable=False: this touches Neo4j, which squashing cannot replay
        # from the Django model state.
        migrations.RunPython(install, uninstall, elidable=False),
    ]
