"""simplejwt's token_blacklist residue is dropped, and the drop is safe.

djangorestframework-simplejwt was removed in 77f9c66, but its tables stayed:
removing an app does not run its migrations backwards. Production kept 406k
expired refresh tokens (216 MB of a 256 MB database), 391k of them minted on
one day in 2022. accounts/migrations/0016_drop_token_blacklist_tables.py drops
the tables and the app's bookkeeping rows, including the rows Wagtail's
reference index (also residue, of a removed app) kept about the tokens.

The first run against the dev database's real data failed at COMMIT on those
reference index rows and rolled back whole, which is why the fixture has them.

The fixture rebuilds the residue as production had it, then migrates over it.
Django's foreign keys are DEFERRABLE INITIALLY DEFERRED, checked only at
commit, and a test never commits: connection.check_constraints() forces the
check, or a wrong deletion order would pass here and fail on production.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, connection

from accounts.models import User

BEFORE = "0015_delete_role"
AFTER = "0016_drop_token_blacklist_tables"
TABLES = {"token_blacklist_outstandingtoken", "token_blacklist_blacklistedtoken"}


def scalar(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def migrate_to(name):
    call_command("migrate", "accounts", name, verbosity=0)


@pytest.fixture
def residue(db):
    """The database as production had it: the app gone, its rows still there."""
    migrate_to(BEFORE)
    user = User.objects.create_superuser("residue", "residue@example.org", "unused")
    group = Group.objects.create(name="residue")

    with connection.cursor() as c:
        # The schema simplejwt 5.x created, foreign keys included.
        c.execute("""
            CREATE TABLE token_blacklist_outstandingtoken (
                id bigserial PRIMARY KEY,
                token text NOT NULL,
                created_at timestamptz,
                expires_at timestamptz NOT NULL,
                user_id uuid REFERENCES accounts_user (id) DEFERRABLE INITIALLY DEFERRED,
                jti varchar(255) NOT NULL UNIQUE
            )""")
        c.execute("""
            CREATE TABLE token_blacklist_blacklistedtoken (
                id bigserial PRIMARY KEY,
                blacklisted_at timestamptz NOT NULL,
                token_id bigint NOT NULL UNIQUE
                    REFERENCES token_blacklist_outstandingtoken (id) DEFERRABLE INITIALLY DEFERRED
            )""")
        c.execute("""
            INSERT INTO token_blacklist_outstandingtoken (token, created_at, expires_at, user_id, jti)
            SELECT 'expired', now() - interval '3 years', now() - interval '3 years', %s, 'jti-' || n
            FROM generate_series(1, 3) AS n""", [user.id])
        c.execute("""
            INSERT INTO token_blacklist_blacklistedtoken (blacklisted_at, token_id)
            SELECT now(), min(id) FROM token_blacklist_outstandingtoken""")
        c.execute("""
            INSERT INTO django_migrations (app, name, applied)
            VALUES ('token_blacklist', '0001_initial', now()),
                   ('token_blacklist', '0012_alter_outstandingtoken_user', now())""")
        c.execute("""
            INSERT INTO django_content_type (app_label, model)
            VALUES ('token_blacklist', 'outstandingtoken'), ('token_blacklist', 'blacklistedtoken')
            RETURNING id""")
        ctypes = [row[0] for row in c.fetchall()]
        c.execute("""
            INSERT INTO auth_permission (name, content_type_id, codename)
            SELECT 'Can view ' || model, id, 'view_' || model
            FROM django_content_type WHERE app_label = 'token_blacklist'
            RETURNING id""")
        permission = c.fetchone()[0]
        c.execute("INSERT INTO auth_group_permissions (group_id, permission_id) VALUES (%s, %s)",
                  [group.id, permission])
        c.execute("INSERT INTO accounts_user_user_permissions (user_id, permission_id) VALUES (%s, %s)",
                  [user.id, permission])
        # What OutstandingTokenAdmin would have logged.
        c.execute("""
            INSERT INTO django_admin_log
                (action_time, object_id, object_repr, action_flag, change_message, content_type_id, user_id)
            VALUES (now(), '1', 'token', 3, '[]', %s, %s)
            RETURNING id""", [ctypes[0], user.id])
        log = c.fetchone()[0]
        # Wagtail's reference index, itself residue of a removed app: one row
        # about a token's reference to its user, one about something else.
        c.execute("""
            CREATE TABLE wagtailcore_referenceindex (
                id serial PRIMARY KEY,
                object_id varchar(255) NOT NULL,
                to_object_id varchar(255) NOT NULL,
                content_type_id integer NOT NULL
                    REFERENCES django_content_type (id) DEFERRABLE INITIALLY DEFERRED,
                base_content_type_id integer NOT NULL
                    REFERENCES django_content_type (id) DEFERRABLE INITIALLY DEFERRED,
                to_content_type_id integer NOT NULL
                    REFERENCES django_content_type (id) DEFERRABLE INITIALLY DEFERRED
            )""")
        c.execute("SELECT id FROM django_content_type WHERE app_label = 'accounts' AND model = 'user'")
        user_ctype = c.fetchone()[0]
        c.execute("""
            INSERT INTO wagtailcore_referenceindex
                (object_id, to_object_id, content_type_id, base_content_type_id, to_content_type_id)
            VALUES ('1', %(user)s, %(token)s, %(token)s, %(user_ct)s),
                   (%(user)s, %(user)s, %(user_ct)s, %(user_ct)s, %(user_ct)s)""",
                  {"user": str(user.id), "token": ctypes[0], "user_ct": user_ctype})

    connection.check_constraints()
    return {"user": user, "group": group, "log": log, "user_ctype": user_ctype}


class TestOnADatabaseWithTheResidue:
    def test_the_tables_are_dropped(self, residue):
        migrate_to(AFTER)
        assert not TABLES & set(connection.introspection.table_names())

    def test_the_bookkeeping_rows_are_gone(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT count(*) FROM django_migrations WHERE app = 'token_blacklist'") == 0
        assert scalar("SELECT count(*) FROM django_content_type WHERE app_label = 'token_blacklist'") == 0
        assert scalar("""SELECT count(*) FROM auth_permission
                         WHERE codename IN ('view_outstandingtoken', 'view_blacklistedtoken')""") == 0

    def test_the_foreign_keys_hold_at_commit(self, residue):
        """The order of the deletions, checked as a real commit would check it."""
        migrate_to(AFTER)
        connection.check_constraints()

    def test_the_user_and_group_survive_without_the_permission(self, residue):
        migrate_to(AFTER)
        user = User.objects.get(pk=residue["user"].pk)
        group = Group.objects.get(pk=residue["group"].pk)
        assert not user.user_permissions.exists()
        assert not group.permissions.exists()

    def test_the_admin_log_entry_is_kept_with_its_content_type_nulled(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT content_type_id FROM django_admin_log WHERE id = %s", [residue["log"]]) is None

    def test_only_the_tokens_reference_index_rows_are_deleted(self, residue):
        migrate_to(AFTER)
        assert scalar("SELECT count(*) FROM wagtailcore_referenceindex") == 1
        assert scalar("SELECT content_type_id FROM wagtailcore_referenceindex") == residue["user_ctype"]

    def test_an_unexpected_reference_fails_rather_than_dangles(self, residue):
        """A reference the migration does not know about must stop it at commit."""
        with connection.cursor() as c:
            c.execute("INSERT INTO taggit_tag (name, slug) VALUES ('residue', 'residue') RETURNING id")
            tag = c.fetchone()[0]
            c.execute("""
                INSERT INTO taggit_taggeditem (object_id, content_type_id, tag_id)
                SELECT 1, min(id), %s FROM django_content_type WHERE app_label = 'token_blacklist'""",
                [tag])
        migrate_to(AFTER)
        with pytest.raises(IntegrityError):
            connection.check_constraints()


class TestOnADatabaseThatNeverHadTheApp:
    def test_the_migration_is_a_no_op(self, db):
        """The test database itself: built from migrations, it never had the app."""
        migrate_to(BEFORE)
        content_types = scalar("SELECT count(*) FROM django_content_type")
        permissions = scalar("SELECT count(*) FROM auth_permission")
        migrate_to(AFTER)
        assert scalar("SELECT count(*) FROM django_content_type") == content_types
        assert scalar("SELECT count(*) FROM auth_permission") == permissions
        connection.check_constraints()

    def test_and_the_tables_are_absent(self, db):
        assert not TABLES & set(connection.introspection.table_names())
