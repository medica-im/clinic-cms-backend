"""Reinstall the timestamp triggers without apoc.trigger.propertiesByKey.

APOC 5 has no such function, so update-insert-timestamp as 0028 installed it
fails on Neo4j 5. The new definition (directory/neo4j_triggers.py) works on 4.4
and 5.
"""
from django.db import migrations


def install(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from directory import neo4j_triggers

    neo4j_triggers.install()


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0034_unset_empty_effector_type_synonyms'),
    ]

    operations = [
        migrations.RunPython(install, migrations.RunPython.noop, elidable=False),
    ]
