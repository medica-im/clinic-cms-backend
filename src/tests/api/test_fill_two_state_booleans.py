"""An effector type's `immaterial` and a directory's `list_owner_entry` hold true or false.

neomodel applies a property's default when it saves a node, so a node written before
the property existed, or by Cypher, had nothing: 129 of dev's 148 effector types had no
`immaterial`, and 14 of its 17 directories no `list_owner_entry`. The code reads a
missing value as the default (`coalesce(t.immaterial, false)`), so nothing displayed
changes; but two servers compared node by node differed on a value that means the same.

A two-state boolean is filled. The entry facets (`free`, `anonymous_care`) are not
touched: for them null means unknown, not false. Run by a directory migration so every
backend gets it on deploy.
"""
import importlib
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import migrations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION = "directory.migrations.0033_fill_two_state_booleans"


@pytest.fixture
async def seeded(neo4j_graph):
    for name, immaterial in {"unset-type": None, "false-type": False, "true-type": True}.items():
        props = {"uid": uuid.uuid4().hex, "name_fr": name}
        if immaterial is not None:
            props["immaterial"] = immaterial
        await neo4j_graph.cypher_query("CREATE (:EffectorType $props)", {"props": props})
    for name, listed in {"unset-dir": None, "false-dir": False, "true-dir": True}.items():
        props = {"uid": uuid.uuid4().hex, "name": name}
        if listed is not None:
            props["list_owner_entry"] = listed
        await neo4j_graph.cypher_query("CREATE (:Directory $props)", {"props": props})
    # A tri-state facet: null is unknown, and must stay so.
    await neo4j_graph.cypher_query("CREATE (:Entry {uid: $uid, slug: 'unknown-free', active: true})",
                                   {"uid": uuid.uuid4().hex})


async def stored(label: str, key: str, name: str) -> bool | None:
    from neomodel import adb

    prop = "name_fr" if label == "EffectorType" else "name"
    rows, _ = await adb.cypher_query(f"MATCH (n:{label} {{{prop}: $name}}) RETURN n.{key}", {"name": name})
    return rows[0][0]


async def run_fix() -> tuple[int, int]:
    from directory.graph_fixes import fill_two_state_booleans

    return await sync_to_async(fill_two_state_booleans)()


class TestTheFix:
    async def test_an_unset_type_is_not_immaterial(self, seeded):
        await run_fix()
        assert await stored("EffectorType", "immaterial", "unset-type") is False

    async def test_an_unset_directory_lists_its_owner_entry(self, seeded):
        await run_fix()
        assert await stored("Directory", "list_owner_entry", "unset-dir") is True

    async def test_values_already_there_are_kept(self, seeded):
        await run_fix()
        assert await stored("EffectorType", "immaterial", "false-type") is False
        assert await stored("EffectorType", "immaterial", "true-type") is True
        assert await stored("Directory", "list_owner_entry", "false-dir") is False
        assert await stored("Directory", "list_owner_entry", "true-dir") is True

    async def test_it_counts_what_it_filled(self, seeded):
        assert await run_fix() == (1, 1)

    async def test_running_it_again_changes_nothing(self, seeded):
        await run_fix()
        assert await run_fix() == (0, 0)

    async def test_a_tri_state_facet_stays_unknown(self, seeded):
        from neomodel import adb

        await run_fix()
        rows, _ = await adb.cypher_query("MATCH (e:Entry {slug: 'unknown-free'}) RETURN e.free, e.anonymous_care")
        assert rows[0] == [None, None]


class TestTheMigration:
    def operation(self):
        module = importlib.import_module(MIGRATION)
        (operation,) = module.Migration.operations
        assert isinstance(operation, migrations.RunPython)
        return operation

    async def test_it_runs_the_fix(self, seeded):
        await sync_to_async(self.operation().code)(None, None)

        assert await stored("EffectorType", "immaterial", "unset-type") is False

    def test_reversing_it_is_a_no_op(self):
        """The default and the missing value mean the same; there is nothing to put back."""
        assert self.operation().reverse_code is migrations.RunPython.noop
