"""Facilities storing "" as a BAN id store null instead.

The API now stores a blank BAN id as null (test_facility_ban_ids.py); this is the
one-off fix for the empty strings already written, run by a directory migration
so every backend gets it on deploy. Only the spelling changes: an id that was
erased stays missing, and restoring those is a separate, reviewed repair.
"""
import importlib
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import migrations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION = "directory.migrations.0032_null_blank_facility_ban_ids"
BAN_ID = "84007_5020_00001"
BAN_BANID = "93507b74-65da-4da8-8028-74ff47dbe1d4"


@pytest.fixture(autouse=True)
def cleared(monkeypatch):
    """The cache endpoints cleared, without needing redis or Postgres."""
    import directory.graph_fixes as graph_fixes

    calls: list[str] = []
    monkeypatch.setattr(graph_fixes, "sync_clear_cache", calls.append)
    return calls


@pytest.fixture
async def seeded(neo4j_graph):
    facilities = {
        "both-blank": ("", ""),
        "banId-blank": (BAN_ID, ""),
        "both-set": (BAN_ID, BAN_BANID),
        "both-null": (None, None),
    }
    for name, (ban_id, ban_banId) in facilities.items():
        await neo4j_graph.cypher_query(
            "CREATE (f:Facility {uid: $uid, name: $name, ban_id: $ban_id, ban_banId: $ban_banId})",
            {"uid": uuid.uuid4().hex, "name": name, "ban_id": ban_id, "ban_banId": ban_banId},
        )


async def stored() -> dict[str, tuple[str | None, str | None]]:
    from neomodel import adb

    rows, _ = await adb.cypher_query("MATCH (f:Facility) RETURN f.name, f.ban_id, f.ban_banId")
    return {name: (ban_id, ban_banId) for name, ban_id, ban_banId in rows}


async def run_fix() -> int:
    from directory.graph_fixes import null_blank_facility_ban_ids

    return await sync_to_async(null_blank_facility_ban_ids)()


class TestTheFix:
    async def test_it_turns_every_empty_string_into_null(self, seeded):
        assert await run_fix() == 2

        after = await stored()
        assert after["both-blank"] == (None, None)
        assert after["banId-blank"] == (BAN_ID, None)

    async def test_it_leaves_real_ids_and_nulls_alone(self, seeded):
        await run_fix()

        after = await stored()
        assert after["both-set"] == (BAN_ID, BAN_BANID)
        assert after["both-null"] == (None, None)

    async def test_running_it_again_changes_nothing(self, seeded):
        await run_fix()
        assert await run_fix() == 0


class TestTheMigration:
    def operation(self):
        module = importlib.import_module(MIGRATION)
        (operation,) = module.Migration.operations
        assert isinstance(operation, migrations.RunPython)
        return operation

    async def test_it_runs_the_fix(self, seeded):
        await sync_to_async(self.operation().code)(None, None)

        assert (await stored())["both-blank"] == (None, None)

    def test_reversing_it_is_a_no_op(self):
        """"" and null both meant no id; there is nothing to put back."""
        assert self.operation().reverse_code is migrations.RunPython.noop
