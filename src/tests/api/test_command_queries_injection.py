"""Management commands pass their values to Cypher as parameters.

They run by hand on a server, with uids, directory names and reasons typed
by an operator or read from a CSV. Spliced into the query text between quotes,
an apostrophe closed the string: `deactivate_entry --reason "changement
d'activité"`, one of its own choices, could never succeed. Every value here
holds an apostrophe, a double quote and a backslash.

export_synonyms writes a Cypher script instead of running queries, so it
escapes; its script must give back exactly what it read.
"""

import asyncio
import contextvars
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

Q = "o'qu\"o\\te"


@pytest.fixture
async def graph(neo4j_graph):
    await adb.cypher_query(
        """
        CREATE (entry:Entry {uid: $q, slug: 'jean', active: true})
        CREATE (e:Effector {uid: $q, name_fr: 'Jean'})
        CREATE (et:EffectorType {uid: $q, name_fr: $q, synonyms_fr: [$q, 'IDE']})
        CREATE (f:Facility {uid: $q, slug: 'cabinet'})
        CREATE (:Directory {name: $q})-[:HAS_ENTRY]->(entry)
        CREATE (entry)-[:HAS_EFFECTOR]->(e), (entry)-[:HAS_EFFECTOR_TYPE]->(et), (entry)-[:HAS_FACILITY]->(f)
        CREATE (e)-[:LOCATION {uid: $q}]->(f)
        """,
        {"q": Q},
    )


async def one(query):
    rows, _ = await adb.cypher_query(query, {"q": Q})
    return rows[0] if rows else None


def command(name):
    from importlib import import_module

    return import_module(f"directory.management.commands.{name}").Command()


async def test_deactivate_entry_with_a_reason_holding_an_apostrophe(graph):
    await sync_to_async(call_command)("deactivate_entry", Q, reason="changement d'activité")

    assert await one("MATCH (e:Entry {uid: $q}) RETURN e.active, e.deactivation_reason") == [
        False, "changement d'activité"
    ]


async def test_delete_entry(graph):
    await sync_to_async(call_command)("delete_entry", Q)

    assert await one("MATCH (e:Entry {uid: $q}) RETURN e") is None


async def test_entry_exists(graph):
    assert await sync_to_async(command("entry_exists").entry_exists)(Q, Q, Q)


async def test_node_contact_update_recognises_an_entry_and_a_facility(graph):
    node_contact_update = command("node_contact_update")
    assert await sync_to_async(node_contact_update.test_is_entry)(Q)
    assert await sync_to_async(node_contact_update.test_is_facility)(Q)


async def test_node_contact_update_points_a_location_contact_at_its_entry(graph):
    contact = SimpleNamespace(neomodel_uid=None, save=lambda: None)

    await sync_to_async(command("node_contact_update").test_is_location)(Q, contact)

    assert contact.neomodel_uid == Q


async def test_read_csv_fixes_a_location_uid(graph):
    await sync_to_async(command("read_csv").fix)(Q, "fixed")

    assert await one("MATCH ()-[l:LOCATION]->() RETURN l.uid") == ["fixed"]


async def test_export_synonyms_writes_a_script_that_gives_them_back(graph, tmp_path):
    """The command runs its own event loop, so it runs here as from a shell:
    on another thread, in an empty context, building its own driver."""
    script = tmp_path / "synonyms.cypher"
    shell = contextvars.Context()
    await asyncio.get_running_loop().run_in_executor(
        None, lambda: shell.run(call_command, "export_synonyms", output=str(script))
    )
    await adb.cypher_query("MATCH (et:EffectorType) SET et.synonyms_fr = []")

    for statement in script.read_text().splitlines():
        await adb.cypher_query(statement)

    assert sorted((await one("MATCH (et:EffectorType) RETURN et.synonyms_fr"))[0]) == sorted([Q, "IDE"])
