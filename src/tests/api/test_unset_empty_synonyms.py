"""An effector type's empty `synonyms_fr` and `synonyms_en` are stored as no property.

The console sent `[]` on every create and the API stored it, so 78 of dev's effector
types held `[]` in `synonyms_en` and 15 in `synonyms_fr`, where the rest held nothing.
The API now stores none as no property (test_effector_type_empty_synonyms.py); this
clears the `[]` already written, run by a directory migration so every backend gets it
on deploy. Types with synonyms are untouched, and so are the synonyms of other nodes
(conditions, situations, needs), which another API writes.
"""
import importlib
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import migrations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION = "directory.migrations.0034_unset_empty_effector_type_synonyms"


@pytest.fixture
async def seeded(neo4j_graph):
    types = {
        "both-empty": {"synonyms_fr": [], "synonyms_en": []},
        "en-empty": {"synonyms_fr": ["IDE"], "synonyms_en": []},
        "filled": {"synonyms_fr": ["IDE"], "synonyms_en": ["nurse"]},
        "unset": {},
    }
    for name, props in types.items():
        await neo4j_graph.cypher_query(
            "CREATE (:EffectorType $props)", {"props": {"uid": uuid.uuid4().hex, "name_fr": name, **props}})
    # Another node's empty synonyms are another API's to write.
    await neo4j_graph.cypher_query(
        "CREATE (:Condition {uid: $uid, name_fr: 'a-condition', synonyms_fr: [], synonyms_en: []})",
        {"uid": uuid.uuid4().hex})


async def stored(name: str) -> tuple:
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        "MATCH (t:EffectorType {name_fr: $name}) RETURN t.synonyms_fr, t.synonyms_en", {"name": name})
    return tuple(rows[0])


async def run_fix() -> int:
    from directory.graph_fixes import unset_empty_effector_type_synonyms

    return await sync_to_async(unset_empty_effector_type_synonyms)()


class TestTheFix:
    async def test_an_empty_list_becomes_no_property(self, seeded):
        await run_fix()
        assert await stored("both-empty") == (None, None)

    async def test_only_the_empty_one_goes(self, seeded):
        await run_fix()
        assert await stored("en-empty") == (["IDE"], None)

    async def test_synonyms_are_kept(self, seeded):
        await run_fix()
        assert await stored("filled") == (["IDE"], ["nurse"])

    async def test_a_type_with_none_stays_as_it_is(self, seeded):
        await run_fix()
        assert await stored("unset") == (None, None)

    async def test_it_counts_the_types_it_changed(self, seeded):
        assert await run_fix() == 2

    async def test_running_it_again_changes_nothing(self, seeded):
        await run_fix()
        assert await run_fix() == 0

    async def test_another_nodes_empty_synonyms_are_left_alone(self, seeded):
        from neomodel import adb

        await run_fix()
        rows, _ = await adb.cypher_query("MATCH (c:Condition {name_fr: 'a-condition'}) RETURN c.synonyms_fr, c.synonyms_en")
        assert rows[0] == [[], []]


class TestTheMigration:
    def operation(self):
        module = importlib.import_module(MIGRATION)
        (operation,) = module.Migration.operations
        assert isinstance(operation, migrations.RunPython)
        return operation

    async def test_it_runs_the_fix(self, seeded):
        await sync_to_async(self.operation().code)(None, None)

        assert await stored("both-empty") == (None, None)

    def test_reversing_it_is_a_no_op(self):
        """`[]` and no property mean the same; there is nothing to put back."""
        assert self.operation().reverse_code is migrations.RunPython.noop
