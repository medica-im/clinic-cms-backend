"""The conditions_v2 endpoint exists on every server once it has been migrated.

Without its Endpoint and AccessControl rows every call to /conditions is a 403,
and the rows are data: nothing in the code creates them. A migration, because
`manage.py migrate` runs on every deploy, on every server.

Everyone reads the mental health tree, only a superuser writes it: it is
reference data every directory's selector is built from, so an administrator or
a staff member must not edit it. It never overwrites: AccessControl is changed
by hand with a .save(), so a row that is already there holds a decision.
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("access", "0011_schedules_v2_access")]
AFTER = [("access", "0012_conditions_v2_access")]

EXPECTED = {
    "superuser": 15,
    "administrator": 1,
    "staff": 1,
    "registered": 1,
    "anonymous": 1,
}


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.fixture
def before_the_migration(transactional_db):
    apps = migrate(BEFORE)
    yield apps
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


def rules(apps):
    AccessControl = apps.get_model("access", "AccessControl")
    return {
        row.role.name: row.permissions
        for row in AccessControl.objects.filter(endpoint__name="conditions_v2").select_related("role")
    }


def test_the_endpoint_and_its_five_rules_are_created(before_the_migration):
    assert rules(before_the_migration) == {}
    assert rules(migrate(AFTER)) == EXPECTED


def test_only_a_superuser_may_write(before_the_migration):
    result = rules(migrate(AFTER))
    assert result["superuser"] == 15
    assert all(permissions == 1 for role, permissions in result.items() if role != "superuser")


def test_migrating_again_changes_nothing(before_the_migration):
    migrate(AFTER)
    migrate(BEFORE)
    migrate(AFTER)
    apps = migrate(AFTER)
    assert rules(apps) == EXPECTED
    assert apps.get_model("access", "Endpoint").objects.filter(name="conditions_v2").count() == 1


def test_a_row_set_by_hand_is_left_as_it_was(before_the_migration):
    apps = before_the_migration
    endpoint = apps.get_model("access", "Endpoint").objects.create(name="conditions_v2")
    administrator = apps.get_model("access", "Role").objects.get(name="administrator")
    apps.get_model("access", "AccessControl").objects.create(endpoint=endpoint, role=administrator, permissions=7)
    result = rules(migrate(AFTER))
    assert result["administrator"] == 7
    assert result["superuser"] == 15


def test_a_role_that_does_not_exist_is_skipped_not_invented(before_the_migration):
    apps = before_the_migration
    apps.get_model("access", "Role").objects.filter(name="registered").delete()
    result = rules(migrate(AFTER))
    assert "registered" not in result
    assert apps.get_model("access", "Role").objects.filter(name="registered").count() == 0
    assert result["anonymous"] == 1


def test_going_back_removes_what_it_created(before_the_migration):
    migrate(AFTER)
    apps = migrate(BEFORE)
    assert apps.get_model("access", "Endpoint").objects.filter(name="conditions_v2").count() == 0
    assert rules(apps) == {}
