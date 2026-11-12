"""COVERS: (entry:Entry)-[:COVERS]->(Commune | DepartmentOfFrance | RegionOfFrance | Country).

Where a service without premises answers: the 3114 covers the country, ÉcoGéPsy a
region. Zero or more per entry; "national" is the Country. It is what an immaterial
entry shows in place of an address. Written through the official driver and checked
before anything is changed: a refusal leaves the entry's edges as they were.
Setting it is part of editing the entry, so whoever may edit the entry may set it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.serializers.entries import update_entry
from api.types.entry import EntryPatch, EntryPost
from api.types.fullentry import FullEntry
from directory.coverage import CoverageRefused, get_coverage, set_coverage

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (:Entry {uid: 'line', active: true, access: 'anonymous'})
        CREATE (:Entry {uid: 'other', active: true, access: 'anonymous'})
        CREATE (:Country {uid: 'fr', name: 'France'})
        CREATE (:RegionOfFrance {uid: 'ara', name: 'Auvergne-Rhône-Alpes'})
        CREATE (:DepartmentOfFrance {uid: 'd69', name: 'Rhône', code: '69'})
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'lyon', name_fr: 'Lyon'})
        CREATE (:Tag {uid: 'nope'})
        """
    )
    return neo4j_graph


async def edges(adb, entry="line"):
    rows, _ = await adb.cypher_query(
        "MATCH (:Entry {uid: $entry})-[:COVERS]->(t) RETURN t.uid ORDER BY t.uid", {"entry": entry}
    )
    return [row[0] for row in rows]


async def test_an_entry_covers_any_level_of_the_territory(graph):
    await set_coverage("line", ["fr", "ara", "d69", "lyon"])
    assert await edges(graph) == ["ara", "d69", "fr", "lyon"]


async def test_the_new_list_replaces_the_old_and_empty_clears(graph):
    await set_coverage("line", ["fr", "ara"])
    await set_coverage("line", ["ara"])
    assert await edges(graph) == ["ara"]
    await set_coverage("line", [])
    assert await edges(graph) == []


async def test_another_entry_is_untouched(graph):
    await set_coverage("other", ["fr"])
    await set_coverage("line", ["ara"])
    assert await edges(graph, "other") == ["fr"]


@pytest.mark.parametrize(
    "entry, uids, code",
    [("nope", ["fr"], "unknown_entry"), ("line", ["nope"], "unknown_place"), ("line", ["fr", "nope"], "unknown_place")],
)
async def test_a_refusal_has_a_code_and_changes_nothing(graph, entry, uids, code):
    await set_coverage("line", ["ara"])
    with pytest.raises(CoverageRefused) as refused:
        await set_coverage(entry, uids)
    assert refused.value.code == code
    assert await edges(graph) == ["ara"]


async def test_it_is_read_with_a_name_and_a_kind(graph):
    await set_coverage("line", ["fr", "d69", "lyon", "ara"])
    assert await get_coverage("line") == [
        {"uid": "fr", "name": "France", "kind": "country"},
        {"uid": "ara", "name": "Auvergne-Rhône-Alpes", "kind": "region"},
        {"uid": "d69", "name": "Rhône", "kind": "department"},
        {"uid": "lyon", "name": "Lyon", "kind": "commune"},
    ]
    assert await get_coverage("other") == []


# --- through the entries API ---------------------------------------------------------


def acting_as(role):
    return (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    )


async def patch_entry(body, role="staff"):
    a, b, c = acting_as(role)
    with a, b, c:
        return await update_entry("line", EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


async def test_whoever_may_edit_the_entry_sets_where_it_answers(graph):
    entry = await patch_entry({"coverage": ["fr"]}, "staff")
    assert entry.coverage == ["fr"]
    assert await edges(graph) == ["fr"]


async def test_a_patch_that_says_nothing_of_it_leaves_it_alone(graph):
    await patch_entry({"coverage": ["fr"]})
    entry = await patch_entry({"active": True})
    assert entry.coverage == ["fr"]


async def test_null_and_empty_both_clear_it(graph):
    await patch_entry({"coverage": ["fr"]})
    assert (await patch_entry({"coverage": None})).coverage == []
    await patch_entry({"coverage": ["fr"]})
    assert (await patch_entry({"coverage": []})).coverage == []


async def test_an_unknown_place_is_a_422_that_writes_nothing_else(graph):
    with pytest.raises(HTTPException) as refused:
        await patch_entry({"coverage": ["nope"], "active": False})
    assert refused.value.status_code == 422
    assert refused.value.detail == {"code": "unknown_place", "uids": ["nope"]}
    rows, _ = await graph.cypher_query("MATCH (e:Entry {uid: 'line'}) RETURN e.active")
    assert rows == [[True]]


def test_the_payloads_and_the_post_body_carry_it():
    base = {"effector": "e", "effector_type": "t", "facility": "f", "memberships": None}
    assert EntryPost(**base).coverage is None
    assert EntryPost(**base, coverage=["fr"]).coverage == ["fr"]
    assert "coverage" in FullEntry.model_fields
