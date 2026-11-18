"""Take label_fr/label_en off the Neo4j Role nodes.

Dropping the columns in 0005 and the properties from the neomodel classes stops
anything *writing* these, but neither deletes what is already stored: a
neomodel class is a description of nodes, not a schema the database enforces.
The five :Role nodes keep their labels until something removes them, and a
half-cleaned node is worse than an uncleaned one — the next person reads
label_fr in the graph, greps for it, finds nothing, and has to work out which
of the two is stale.

Safe to run: these nodes have no relationships of any kind, and access is
resolved through a `role` string property on :Access rather than through them.
Nothing reads the properties this removes.

Lives in the access app's migration history because it belongs to the same
change as 0005, and because there is nowhere else that runs once per deploy.
"""
from django.db import migrations


def strip_labels(apps, schema_editor):
    # Imported here rather than at module scope: a migration module is loaded
    # by makemigrations on machines with no Neo4j to connect to.
    from neomodel import db

    db.cypher_query(
        "MATCH (r:Role) "
        "WHERE r.label_fr IS NOT NULL OR r.label_en IS NOT NULL "
        "REMOVE r.label_fr, r.label_en"
    )


def restore_labels(apps, schema_editor):
    # Deliberately not reversible. The values came from Postgres columns that
    # 0005 drops, so there is nothing left to copy back; re-adding them would
    # mean inventing strings the frontend already owns.
    raise migrations.exceptions.IrreversibleError(
        "Role labels were removed from the graph and their source columns "
        "dropped. Role display text lives in the frontend "
        "(messages/*.json, src/lib/roles.ts)."
    )


class Migration(migrations.Migration):

    dependencies = [
        ('access', '0005_remove_role_label_remove_role_label_en_and_more'),
    ]

    operations = [
        migrations.RunPython(strip_labels, restore_labels),
    ]
