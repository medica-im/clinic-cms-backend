"""Facilities stored at 0/0 lose their point.

A migration rather than a command because `migrate` is what runs once on every
backend at deploy (see 0028). Idempotent, and it only touches 0/0 points, so it
is harmless when pytest-django runs it while building a test database.
"""
from django.db import migrations


def null_zero_locations(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from directory.graph_fixes import null_zero_facility_locations

    count = null_zero_facility_locations()
    print(f"\n  {count} facilities at 0/0 now have no location")


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0030_entryslug'),
    ]

    operations = [
        migrations.RunPython(null_zero_locations, migrations.RunPython.noop),
    ]
