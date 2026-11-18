"""Repair the graph to one active Access per user and site, then constrain it.

A migration because `manage.py migrate` runs on every deploy, on every server,
so no database keeps the duplicates or misses the constraint the code now
relies on. The rules — which duplicate is deleted, which is retired — live in
access/active_access.py with the tests that pin them.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def enforce(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from access.active_access import enforce_single_active_access

    counts = enforce_single_active_access()
    logger.warning(f"single active Access per user and site: {counts}")


class Migration(migrations.Migration):

    dependencies = [
        ('access', '0006_strip_role_labels_from_graph'),
    ]

    operations = [
        # elidable=False: this touches Neo4j, which squashing cannot replay
        # from the Django model state.
        migrations.RunPython(enforce, migrations.RunPython.noop, elidable=False),
    ]
