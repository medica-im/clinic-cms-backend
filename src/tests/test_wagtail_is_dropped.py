"""Wagtail's residue is dropped, and only Wagtail's.

Wagtail and the cms app built on it were removed in 16a2c04, but their 42
tables stayed, with their bookkeeping rows, Wagtail's default groups and
taggit links to its images. accounts/migrations/0017_drop_wagtail_tables.py
removes them.

The fixture rebuilds a small version of that residue beside live data the
migration must leave alone: a tag a live model also uses, a group with a
member, a group holding a live permission. As in
tests/test_token_blacklist_is_dropped.py, connection.check_constraints() stands
in for the commit a test never reaches.
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import InternalError, connection

from accounts.models import User

BEFORE = "0016_drop_token_blacklist_tables"
AFTER = "0017_drop_wagtail_tables"
PREFIXES = ("wagtail", "cms_")


def scalar(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def migrate_to(name):
    call_command("migrate", "accounts", name, verbosity=0)


def wagtail_tables():
    return {t for t in connection.introspection.table_names() if t.startswith(PREFIXES)}


@pytest.fixture
def residue(db):
    migrate_to(BEFORE)
    member = User.objects.create_superuser("member", "member@example.org", "unused")
    live_permission = Permission.objects.get(codename="view_user")

    with connection.cursor() as c:
        # Foreign keys among the tables, as Wagtail's own: a page subclass
        # points at its page, the page at its content type.
        c.execute("""
            CREATE TABLE wagtailcore_page (
                id serial PRIMARY KEY,
                title varchar(255) NOT NULL,
                content_type_id integer NOT NULL
                    REFERENCES django_content_type (id) DEFERRABLE INITIALLY DEFERRED
            )""")
        c.execute("""
            CREATE TABLE cms_homepage (
                page_ptr_id integer PRIMARY KEY
                    REFERENCES wagtailcore_page (id) DEFERRABLE INITIALLY DEFERRED
            )""")
        c.execute("CREATE TABLE wagtailimages_image (id serial PRIMARY KEY, file varchar(100) NOT NULL)")
        c.execute("""
            INSERT INTO django_content_type (app_label, model)
            VALUES ('wagtailcore', 'page'), ('cms', 'homepage'), ('wagtailimages', 'image')
            RETURNING id""")
        page_ct, homepage_ct, image_ct = (row[0] for row in c.fetchall())
        c.execute("INSERT INTO wagtailcore_page (title, content_type_id) VALUES ('Home', %s) RETURNING id",
                  [homepage_ct])
        c.execute("INSERT INTO cms_homepage (page_ptr_id) VALUES (%s)", [c.fetchone()[0]])
        c.execute("INSERT INTO wagtailimages_image (file) VALUES ('original_images/a.jpg') RETURNING id")
        image = c.fetchone()[0]
        c.execute("""
            INSERT INTO django_migrations (app, name, applied)
            VALUES ('wagtailcore', '0001_initial', now()), ('cms', '0001_initial', now())""")
        c.execute("""
            INSERT INTO auth_permission (name, content_type_id, codename)
            VALUES ('Can change page', %s, 'change_page'), ('Can add image', %s, 'add_image')
            RETURNING id""", [page_ct, image_ct])
        wagtail_permission = c.fetchone()[0]
        c.execute("INSERT INTO django_admin_log (action_time, object_id, object_repr, action_flag,"
                  " change_message, content_type_id, user_id)"
                  " VALUES (now(), '1', 'Home', 2, '[]', %s, %s) RETURNING id", [page_ct, member.id])
        log = c.fetchone()[0]

        # taggit: a tag only an image uses, and one a live model uses too.
        c.execute("INSERT INTO taggit_tag (name, slug) VALUES ('vedene', 'vedene'), ('shared', 'shared')"
                  " RETURNING id")
        wagtail_only, shared = (row[0] for row in c.fetchall())
        user_ct = scalar("SELECT id FROM django_content_type WHERE app_label = 'accounts' AND model = 'user'")
        c.execute("""
            INSERT INTO taggit_taggeditem (object_id, content_type_id, tag_id)
            VALUES (%(image)s, %(image_ct)s, %(wagtail_only)s),
                   (%(image)s, %(image_ct)s, %(shared)s),
                   (1, %(user_ct)s, %(shared)s)""",
                  {"image": image, "image_ct": image_ct, "wagtail_only": wagtail_only,
                   "shared": shared, "user_ct": user_ct})

    moderators = Group.objects.create(name="Moderators")
    editors = Group.objects.create(name="Editors")
    staff = Group.objects.create(name="Staff")
    for group in (moderators, editors, staff):
        group.permissions.add(wagtail_permission)
    staff.permissions.add(live_permission)
    member.groups.add(editors)
    member.user_permissions.add(wagtail_permission)

    connection.check_constraints()
    return {"member": member, "log": log, "wagtail_only": wagtail_only, "shared": shared,
            "live_permission": live_permission}


class TestOnADatabaseWithTheResidue:
    def test_every_table_is_dropped(self, residue):
        assert wagtail_tables()
        migrate_to(AFTER)
        assert not wagtail_tables()

    def test_the_bookkeeping_rows_are_gone(self, residue):
        migrate_to(AFTER)
        removed = "('cms', 'wagtailcore', 'wagtailimages')"
        assert scalar(f"SELECT count(*) FROM django_migrations WHERE app IN {removed}") == 0
        assert scalar(f"SELECT count(*) FROM django_content_type WHERE app_label IN {removed}") == 0
        assert scalar("SELECT count(*) FROM auth_permission WHERE codename IN ('change_page', 'add_image')") == 0

    def test_the_foreign_keys_hold_at_commit(self, residue):
        migrate_to(AFTER)
        connection.check_constraints()

    def test_wagtails_default_group_goes(self, residue):
        migrate_to(AFTER)
        assert not Group.objects.filter(name="Moderators").exists()

    def test_a_default_group_with_a_member_stays(self, residue):
        migrate_to(AFTER)
        editors = Group.objects.get(name="Editors")
        assert not editors.permissions.exists()
        assert residue["member"] in editors.user_set.all()

    def test_a_default_group_given_a_live_permission_stays(self, residue):
        """The name alone is not enough: someone may have reused the group."""
        Group.objects.get(name="Moderators").permissions.add(residue["live_permission"])
        migrate_to(AFTER)
        moderators = Group.objects.get(name="Moderators")
        assert list(moderators.permissions.all()) == [residue["live_permission"]]

    def test_a_group_keeps_its_live_permissions(self, residue):
        migrate_to(AFTER)
        assert list(Group.objects.get(name="Staff").permissions.all()) == [residue["live_permission"]]

    def test_the_user_loses_only_the_wagtail_permission(self, residue):
        migrate_to(AFTER)
        assert not User.objects.get(pk=residue["member"].pk).user_permissions.exists()

    def test_a_tag_only_wagtail_used_goes(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT count(*) FROM taggit_tag WHERE id = %s", [residue["wagtail_only"]]) == 0

    def test_a_tag_a_live_model_uses_stays_with_its_live_link(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT count(*) FROM taggit_tag WHERE id = %s", [residue["shared"]]) == 1
        assert scalar("SELECT count(*) FROM taggit_taggeditem WHERE tag_id = %s", [residue["shared"]]) == 1

    def test_the_admin_log_entry_is_kept_with_its_content_type_nulled(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT content_type_id FROM django_admin_log WHERE id = %s", [residue["log"]]) is None

    def test_a_live_foreign_key_into_the_residue_stops_the_drop(self, residue):
        """Without CASCADE, a live table pointing in fails the DROP itself."""
        with connection.cursor() as c:
            c.execute("CREATE TABLE live_thing (id serial PRIMARY KEY,"
                      " image_id integer REFERENCES wagtailimages_image (id))")
        with pytest.raises(InternalError, match="depend"):
            migrate_to(AFTER)


class TestOnADatabaseThatNeverHadTheApps:
    def test_the_migration_is_a_no_op(self, db):
        migrate_to(BEFORE)
        counts = [scalar(f"SELECT count(*) FROM {t}")
                  for t in ("django_content_type", "auth_permission", "auth_group", "taggit_tag")]
        migrate_to(AFTER)
        assert [scalar(f"SELECT count(*) FROM {t}")
                for t in ("django_content_type", "auth_permission", "auth_group", "taggit_tag")] == counts
        connection.check_constraints()
