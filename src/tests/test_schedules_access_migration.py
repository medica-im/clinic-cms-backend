"""The schedules_v2 endpoint exists on every server once it has been migrated.

Without its Endpoint and AccessControl rows every call to /schedules is a 403,
and the rows are data: nothing in the code creates them. A migration, because
`manage.py migrate` runs on every deploy, on every server.

It never overwrites. AccessControl is changed by hand with a .save(), so a row
that is already there holds a decision this migration must not undo.
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("access", "0010_batch_job_kind")]
AFTER = [("access", "0011_schedules_v2_access")]

EXPECTED = {
    "superuser": 15,
    "administrator": 15,
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
        for row in AccessControl.objects.filter(endpoint__name="schedules_v2").select_related("role")
    }


def test_the_endpoint_and_its_five_rules_are_created(before_the_migration):
    assert rules(before_the_migration) == {}
    assert rules(migrate(AFTER)) == EXPECTED


def test_staff_may_read_but_not_write_so_that_only_the_entrys_people_can(before_the_migration):
    assert rules(migrate(AFTER))["staff"] == 1


def test_migrating_again_changes_nothing(before_the_migration):
    migrate(AFTER)
    migrate(BEFORE)
    migrate(AFTER)
    apps = migrate(AFTER)
    assert rules(apps) == EXPECTED
    assert apps.get_model("access", "Endpoint").objects.filter(name="schedules_v2").count() == 1


def test_a_row_set_by_hand_is_left_as_it_was(before_the_migration):
    apps = before_the_migration
    endpoint = apps.get_model("access", "Endpoint").objects.create(name="schedules_v2")
    staff = apps.get_model("access", "Role").objects.get(name="staff")
    apps.get_model("access", "AccessControl").objects.create(endpoint=endpoint, role=staff, permissions=3)
    result = rules(migrate(AFTER))
    assert result["staff"] == 3
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
    assert apps.get_model("access", "Endpoint").objects.filter(name="schedules_v2").count() == 0
    assert rules(apps) == {}
