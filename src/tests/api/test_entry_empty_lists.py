"""An entry's payment methods and third-party payers: nothing is no property, never `[]`.

The two lists are stored on the Entry node. The importer stored nothing as no property,
the clone stored `[]`, and the entry edit stored whatever the form sent (`[]` when
everything is unticked, `null` from « delete »), so the graph held both: on staging
133 entries had `[]` where dev's 735 had nothing. The page reads the same either way
(the full entry matches payers with `IN entry.third_party_payer` and turns an empty
match into `None`), so one convention costs the reader nothing: an empty list is no
property, like the facets, where null means unknown.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.serializers.entries import update_entry
from api.types.entry import EntryPatch

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query("CREATE (:Entry {uid: 'alsm', active: true, access: 'anonymous'})")
    return neo4j_graph


async def patch_entry(body):
    with (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value="staff")),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    ):
        return await update_entry("alsm", EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


async def stored(adb):
    rows, _ = await adb.cypher_query("MATCH (e:Entry {uid: 'alsm'}) RETURN e.payment, e.third_party_payer")
    return rows[0]


@pytest.mark.parametrize("empty", [[], None])
async def test_emptying_both_lists_leaves_no_property(graph, empty):
    await patch_entry({"payment": ["Carte bancaire"], "third_party_payer": ["CPAM"]})
    await patch_entry({"payment": empty, "third_party_payer": empty})
    assert await stored(graph) == [None, None]


async def test_filled_lists_are_stored_as_sent(graph):
    await patch_entry({"payment": ["Carte bancaire", "Espèces"], "third_party_payer": ["CPAM"]})
    assert await stored(graph) == [["Carte bancaire", "Espèces"], ["CPAM"]]


async def test_silence_keeps_what_is_stored(graph):
    await patch_entry({"payment": ["Carte bancaire"]})
    await patch_entry({"free": True})
    assert (await stored(graph))[0] == ["Carte bancaire"]


async def test_an_empty_list_for_one_leaves_the_other_alone(graph):
    await patch_entry({"payment": ["Carte bancaire"], "third_party_payer": ["CPAM"]})
    await patch_entry({"payment": []})
    assert await stored(graph) == [None, ["CPAM"]]
