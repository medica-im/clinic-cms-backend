"""Drop what Wagtail, and the cms app built on it, left behind.

Wagtail was removed in 16a2c04, along with cms, whose page models extended
Wagtail's. Removing an app does not remove its tables, so 42 tables stayed,
with the apps' django_migrations, content type and permission rows, Wagtail's
default Moderators and Editors groups, and taggit links to its images and
documents. See tests/test_wagtail_is_dropped.py.

The tables are found by app label prefix rather than listed, since databases
that went through different Wagtail versions hold different tables. They are
dropped in one statement without CASCADE: foreign keys among them are fine,
and one from any other table makes the migration fail rather than quietly
drop that table's constraint. Every statement matches nothing on a database
that never had these apps.

taggit stays installed: only the links to the dropped models go, and the tags
nothing else uses. A group goes only if it is one of Wagtail's defaults and is
left with no members and no permissions.

The image and document files in media are not touched: a migration runs on
every server, and each keeps its media elsewhere.

Not reversible in substance: the reverse is a no-op.
"""

from django.db import migrations

REMOVED = [
    'cms',
    'wagtailadmin',
    'wagtailcore',
    'wagtaildocs',
    'wagtailembeds',
    'wagtailforms',
    'wagtailimages',
    'wagtailredirects',
    'wagtailsearch',
    'wagtailusers',
]

LABELS = ", ".join(f"'{label}'" for label in REMOVED)
# An escaped underscore: 'cms_%' would also match 'cmsx'.
PREFIXES = "ARRAY[" + ", ".join(f"'{label}\\_%'" for label in REMOVED) + "]"
STALE = f"SELECT id FROM django_content_type WHERE app_label IN ({LABELS})"
STALE_PERMISSIONS = f"SELECT id FROM auth_permission WHERE content_type_id IN ({STALE})"

STATEMENTS = [
    f"""
    DO $$
    DECLARE tables text;
    BEGIN
        SELECT string_agg(format('%I', tablename), ', ') INTO tables
        FROM pg_tables
        WHERE schemaname = current_schema() AND tablename LIKE ANY ({PREFIXES});
        IF tables IS NOT NULL THEN
            EXECUTE 'DROP TABLE ' || tables;
        END IF;
    END $$
    """,
    f"DELETE FROM django_migrations WHERE app IN ({LABELS})",
    # The CTE's delete is not visible to the outer query, which therefore
    # still sees the other models' links: a tag one of them uses is kept.
    f"""
    WITH unlinked AS (
        DELETE FROM taggit_taggeditem WHERE content_type_id IN ({STALE}) RETURNING tag_id
    )
    DELETE FROM taggit_tag
    WHERE id IN (SELECT tag_id FROM unlinked)
      AND id NOT IN (SELECT tag_id FROM taggit_taggeditem WHERE content_type_id NOT IN ({STALE}))
    """,
    f"DELETE FROM auth_group_permissions WHERE permission_id IN ({STALE_PERMISSIONS})",
    f"DELETE FROM accounts_user_user_permissions WHERE permission_id IN ({STALE_PERMISSIONS})",
    """
    DELETE FROM auth_group g
    WHERE name IN ('Moderators', 'Editors')
      AND NOT EXISTS (SELECT 1 FROM auth_group_permissions WHERE group_id = g.id)
      AND NOT EXISTS (SELECT 1 FROM accounts_user_groups WHERE group_id = g.id)
    """,
    f"DELETE FROM auth_permission WHERE content_type_id IN ({STALE})",
    f"UPDATE django_admin_log SET content_type_id = NULL WHERE content_type_id IN ({STALE})",
    f"DELETE FROM django_content_type WHERE app_label IN ({LABELS})",
]


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_drop_token_blacklist_tables'),
        ('taggit', '0006_rename_taggeditem_content_type_object_id_taggit_tagg_content_8fc721_idx'),
    ]

    operations = [
        migrations.RunSQL(STATEMENTS, reverse_sql=migrations.RunSQL.noop),
    ]
