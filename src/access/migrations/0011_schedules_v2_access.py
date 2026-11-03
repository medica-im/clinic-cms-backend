"""Open the schedules_v2 endpoint: read for everyone, write for the entry's people.

Opening hours are public, so every role reads (1). Writing is left to
administrators and superusers (15) and, through authorize_api's object-level
check, to the owners and creators of the entry. Staff hold 1, not 4 or 8: a
random staff member must not be able to edit a random entry's hours.

A migration because `manage.py migrate` runs on every deploy, on every server,
and these rows are data that nothing else creates. It only adds: an existing
row was set by hand and holds a decision, so it is never overwritten. A role
that does not exist is skipped rather than invented.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

ENDPOINT = "schedules_v2"
PERMISSIONS = {
    "superuser": 15,
    "administrator": 15,
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
        ("access", "0010_batch_job_kind"),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]
