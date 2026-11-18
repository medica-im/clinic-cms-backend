"""Facilities storing "" as a BAN id store null instead.

Only the spelling of "no id" changes. Ids erased by the facility page's edit
dialog stay missing; restoring them is a separate, reviewed repair.
"""
from django.db import migrations


def null_blank_ban_ids(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from directory.graph_fixes import null_blank_facility_ban_ids

    count = null_blank_facility_ban_ids()
    print(f"\n  {count} facilities had an empty BAN id, now null")


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0031_null_zero_facility_locations'),
    ]

    operations = [
        migrations.RunPython(null_blank_ban_ids, migrations.RunPython.noop),
    ]
