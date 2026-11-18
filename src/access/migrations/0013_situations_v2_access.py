"""Open the situations_v2 endpoint: read for everyone, write for superusers.

The situations tree (life circumstances, their PART_OF parents, what they may
lead to and the Needs they impact) is reference data like the conditions tree:
the console writes it and every directory's selector is built from it, so every
role reads it (1) and only a superuser writes it (15).

A migration for the same reasons as 0012: it runs on every server, only adds,
never overwrites a row set by hand, and skips a role that does not exist.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

ENDPOINT = "situations_v2"
PERMISSIONS = {
    "superuser": 15,
    "administrator": 1,
    "staff": 1,
    "registered": 1,
    "anonymous": 1,
}


def grant(apps, schema_editor):
    Endpoint = apps.get_model("access", "Endpoint")
    Role = apps.get_model("access", "Role")
    AccessControl = apps.get_model("access", "AccessControl")
    endpoint, _ = Endpoint.objects.get_or_create(name=ENDPOINT)
    for name, permissions in PERMISSIONS.items():
        role = Role.objects.filter(name=name).first()
        if role is None:
            logger.warning(f"{ENDPOINT}: no role named {name!r}, no access row created for it")
            continue
        AccessControl.objects.get_or_create(
            endpoint=endpoint, role=role, defaults={"permissions": permissions}
        )


def revoke(apps, schema_editor):
    apps.get_model("access", "Endpoint").objects.filter(name=ENDPOINT).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0012_conditions_v2_access"),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]
