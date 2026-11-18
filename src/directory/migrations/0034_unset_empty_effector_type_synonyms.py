"""An effector type with no synonyms stores no property, not `[]`.

Only the spelling of "none" changes: readers already took both as none.
"""
from django.db import migrations


def unset_empty_synonyms(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from directory.graph_fixes import unset_empty_effector_type_synonyms

    count = unset_empty_effector_type_synonyms()
    print(f"\n  {count} effector types had empty synonyms, now none")


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0033_fill_two_state_booleans'),
    ]

    operations = [
        migrations.RunPython(unset_empty_synonyms, migrations.RunPython.noop),
    ]
