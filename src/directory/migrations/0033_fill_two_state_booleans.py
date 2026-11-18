"""An effector type's `immaterial` and a directory's `list_owner_entry` hold true or false.

Only the spelling of the default changes: readers already took a missing value as
the default.
"""
from django.db import migrations


def fill_two_state_booleans(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from directory.graph_fixes import fill_two_state_booleans

    types, directories = fill_two_state_booleans()
    print(f"\n  {types} effector types had no immaterial, {directories} directories no list_owner_entry")


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0032_null_blank_facility_ban_ids'),
    ]

    operations = [
        migrations.RunPython(fill_two_state_booleans, migrations.RunPython.noop),
    ]
