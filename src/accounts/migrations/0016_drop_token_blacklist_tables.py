"""Drop what djangorestframework-simplejwt's token_blacklist app left behind.

The library was removed in 77f9c66, but removing an app from INSTALLED_APPS
does not remove its tables: its migrations never run again, so nothing ever
drops them. On production that left 406k expired refresh tokens, 216 MB of a
256 MB database, plus the app's django_migrations, content type and permission
rows. See tests/test_token_blacklist_is_dropped.py.

Raw SQL because Django no longer knows these models. Every statement matches
nothing on a database that never had the app, so this is a no-op there.

The foreign keys into django_content_type and auth_permission are NO ACTION in
the database (Django emulates its cascades in Python), so rows are removed in
dependency order. Admin log entries are kept with their content type nulled,
as the field's on_delete=SET_NULL would. Any other reference to these content
types makes the migration fail and roll back whole, rather than guess.

wagtailcore_referenceindex is residue too: Wagtail was removed in 16a2c04,
and the index it kept had 1416 rows describing the tokens' references to their
users. It is derived data, and the table may not exist at all, so its rows
are deleted only where it does.

Not reversible in substance: the reverse is a no-op so the accounts migrations
can still be walked back past this one.
"""

from django.db import migrations

STALE = "SELECT id FROM django_content_type WHERE app_label = 'token_blacklist'"
STALE_PERMISSIONS = f"SELECT id FROM auth_permission WHERE content_type_id IN ({STALE})"

STATEMENTS = [
    # blacklistedtoken has a foreign key into outstandingtoken: it goes first.
    "DROP TABLE IF EXISTS token_blacklist_blacklistedtoken",
    "DROP TABLE IF EXISTS token_blacklist_outstandingtoken",
    "DELETE FROM django_migrations WHERE app = 'token_blacklist'",
    f"DELETE FROM auth_group_permissions WHERE permission_id IN ({STALE_PERMISSIONS})",
    f"DELETE FROM accounts_user_user_permissions WHERE permission_id IN ({STALE_PERMISSIONS})",
    f"DELETE FROM auth_permission WHERE content_type_id IN ({STALE})",
    f"UPDATE django_admin_log SET content_type_id = NULL WHERE content_type_id IN ({STALE})",
    f"""
    DO $$ BEGIN
        IF to_regclass('wagtailcore_referenceindex') IS NOT NULL THEN
            DELETE FROM wagtailcore_referenceindex
            WHERE content_type_id IN ({STALE})
               OR base_content_type_id IN ({STALE})
               OR to_content_type_id IN ({STALE});
        END IF;
    END $$
    """,
    "DELETE FROM django_content_type WHERE app_label = 'token_blacklist'",
]


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_delete_role'),
        # The tables the statements touch must exist, even on a fresh database.
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunSQL(STATEMENTS, reverse_sql=migrations.RunSQL.noop),
    ]
