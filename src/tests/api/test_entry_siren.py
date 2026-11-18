"""The SIREN of an entry that is a legal unit (a porteur such as MGEN).

Like run_by it is a claim about legal identity, so only administrators and
superusers write it; and it must agree with the SIRET of every service the entry
runs. Stored on the Entry node, returned with it, removed by sending null.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.serializers.entries import update_entry
from api.serializers.fullentry import add_entries_around
from api.types.entry import EntryPatch

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MGEN = "441921913"
RIVAL = "123456782"


@pytest.fixture
async def graph(neo4j_graph):
    """MGEN, and an establishment of it at a facility that has a SIRET."""
    await neo4j_graph.cypher_query(
        """
        CREATE (m:Entry {uid: 'mgen', active: true, access: 'anonymous'})
        CREATE (l:Entry {uid: 'lyon', active: true, access: 'anonymous'})
        CREATE (l)-[:HAS_FACILITY]->(:Facility {uid: 'f', siret: '44192191300212'})
        CREATE (l)-[:RUN_BY]->(m)
        """
    )
    return neo4j_graph


async def patch_entry(uid, body, role):
    with (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    ):
        return await update_entry(uid, EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


async def stored(adb):
    rows, _ = await adb.cypher_query("MATCH (e:Entry {uid: 'mgen'}) RETURN e.siren")
    return rows[0][0]


@pytest.mark.parametrize("role", ["administrator", "superuser"])
async def test_an_administrator_or_a_superuser_sets_the_siren(graph, role):
    entry = await patch_entry("mgen", {"siren": "441 921 913"}, role)
    assert entry.siren == MGEN
    assert await stored(graph) == MGEN


@pytest.mark.parametrize("role", ["staff", "registered", None])
async def test_nobody_else_may_and_nothing_is_written(graph, role):
    with pytest.raises(HTTPException) as refused:
        await patch_entry("mgen", {"siren": MGEN}, role)
    assert refused.value.status_code == 403
    assert await stored(graph) is None


async def test_a_siren_that_disagrees_with_a_services_siret_is_a_409_and_changes_nothing(graph):
    with pytest.raises(HTTPException) as refused:
        await patch_entry("mgen", {"siren": RIVAL}, "superuser")
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "siret_mismatch"}
    assert await stored(graph) is None


async def test_null_removes_the_siren_and_silence_keeps_it(graph):
    await patch_entry("mgen", {"siren": MGEN}, "administrator")
    kept = await patch_entry("mgen", {"active": True}, "staff")
    assert kept.siren == MGEN
    removed = await patch_entry("mgen", {"siren": None}, "administrator")
    assert removed.siren is None
    assert await stored(graph) is None


async def test_a_page_shows_the_siren_of_its_porteur_so_the_link_is_explained(graph):
    await patch_entry("mgen", {"siren": MGEN}, "administrator")
    await graph.cypher_query(
        """
        MATCH (m:Entry {uid: 'mgen'}), (l:Entry {uid: 'lyon'})
        CREATE (m)-[:HAS_EFFECTOR]->(:Effector {uid: 'e1', name_fr: 'MGEN Action sanitaire et sociale'})
        CREATE (l)-[:HAS_EFFECTOR]->(:Effector {uid: 'e2', name_fr: 'ESM Lyon'})
        """
    )
    page = {}
    await add_entries_around(page, "lyon", "anonymous")
    assert page["run_by"]["siren"] == MGEN
