"""Setting an entry's porteur through the entries API.

Saying "this entry is run by MGEN" publishes a claim on MGEN's page, so it is an
administrator's or a superuser's to make, as the directories of an entry are:
a staff member who owns an entry may not attach it to someone else's. The graph
rules (one edge, no loop) are pinned in test_run_by.py; what is pinned here is
who may write it, how a refusal is worded for the page, and that PATCH and
POST both go through the same function.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.serializers.entries import apply_run_by, update_entry
from api.serializers.fullentry import add_entries_around
from api.types.entry import EntryPatch, EntryPost

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        "UNWIND ['mgen', 'lyon', 'other'] AS uid CREATE (:Entry {uid: uid, active: true, access: 'anonymous'})"
    )
    return neo4j_graph


async def edges(adb):
    rows, _ = await adb.cypher_query("MATCH (e:Entry)-[:RUN_BY]->(p:Entry) RETURN e.uid, p.uid ORDER BY e.uid")
    return rows


@pytest.mark.parametrize("role", ["administrator", "superuser"])
async def test_an_administrator_or_a_superuser_sets_the_porteur(graph, role):
    await apply_run_by("lyon", "mgen", role)
    assert await edges(graph) == [["lyon", "mgen"]]


@pytest.mark.parametrize("role", ["staff", "registered", "anonymous", None])
async def test_nobody_else_may_set_it_and_nothing_is_written(graph, role):
    with pytest.raises(HTTPException) as refused:
        await apply_run_by("lyon", "mgen", role)
    assert refused.value.status_code == 403
    assert await edges(graph) == []


@pytest.mark.parametrize(
    "entry, porteur, status, code",
    [
        ("nope", "mgen", 404, "unknown_entry"),
        ("lyon", "nope", 422, "unknown_porteur"),
        ("lyon", "lyon", 409, "cycle"),
    ],
)
async def test_a_refusal_is_a_status_and_a_code_the_page_can_word(graph, entry, porteur, status, code):
    with pytest.raises(HTTPException) as refused:
        await apply_run_by(entry, porteur, "superuser")
    assert refused.value.status_code == status
    assert refused.value.detail == {"code": code}
    assert await edges(graph) == []


async def test_a_loop_is_a_409_and_keeps_the_chain(graph):
    await apply_run_by("lyon", "mgen", "superuser")
    with pytest.raises(HTTPException) as refused:
        await apply_run_by("mgen", "lyon", "superuser")
    assert refused.value.status_code == 409
    assert await edges(graph) == [["lyon", "mgen"]]


def acting_as(role):
    return (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    )


async def patch_entry(uid, body, role):
    a, b, c = acting_as(role)
    with a, b, c:
        return await update_entry(uid, EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


async def test_patching_an_entry_sets_its_porteur_and_the_response_names_it(graph):
    entry = await patch_entry("lyon", {"run_by": "mgen"}, "administrator")
    assert entry.run_by == "mgen"
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_patching_run_by_to_null_detaches_it(graph):
    await patch_entry("lyon", {"run_by": "mgen"}, "administrator")
    entry = await patch_entry("lyon", {"run_by": None}, "administrator")
    assert entry.run_by is None
    assert await edges(graph) == []


async def test_a_patch_that_says_nothing_of_run_by_leaves_it_alone(graph):
    await patch_entry("lyon", {"run_by": "mgen"}, "administrator")
    entry = await patch_entry("lyon", {"active": True}, "staff")
    assert entry.run_by == "mgen"
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_a_staff_owner_patching_run_by_is_refused_and_changes_nothing_else(graph):
    with pytest.raises(HTTPException) as refused:
        await patch_entry("lyon", {"run_by": "mgen", "active": False}, "staff")
    assert refused.value.status_code == 403
    assert await edges(graph) == []
    rows, _ = await graph.cypher_query("MATCH (e:Entry {uid: 'lyon'}) RETURN e.active")
    assert rows == [[True]]


async def test_the_post_body_accepts_a_porteur_and_the_default_is_none():
    base = {"effector": "e", "effector_type": "t", "facility": "f", "memberships": None}
    assert EntryPost(**base).run_by is None
    assert EntryPost(**base, run_by="mgen").run_by == "mgen"


# --- The full entry carries its porteur and its services ------------------------------


async def seed_named(adb):
    await adb.cypher_query(
        """
        MATCH (m:Entry {uid: 'mgen'}), (l:Entry {uid: 'lyon'}), (o:Entry {uid: 'other'})
        SET m.slug = 'mgen', l.slug = 'esm-lyon', o.slug = 'secret', o.access = 'administrator'
        CREATE (m)-[:HAS_EFFECTOR]->(:Effector {uid: 'e1', name_fr: 'MGEN Action sanitaire et sociale', label_fr: 'MGEN'})
        CREATE (m)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't1', label_fr: 'organisme mutualiste'})
        CREATE (l)-[:HAS_EFFECTOR]->(:Effector {uid: 'e2', name_fr: 'Établissement de santé mentale de Lyon', label_fr: 'ESM Lyon'})
        CREATE (l)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't2', label_fr: 'hôpital de jour'})
        CREATE (o)-[:HAS_EFFECTOR]->(:Effector {uid: 'e3', name_fr: 'Annexe réservée', label_fr: 'Annexe'})
        CREATE (o)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't3', label_fr: 'hôpital de jour'})
        """
    )
    await apply_run_by("lyon", "mgen", "superuser")
    await apply_run_by("other", "mgen", "superuser")


async def test_a_page_gets_its_porteur_as_a_link_the_site_language_can_read(graph):
    await seed_named(graph)
    entry = {"uid": "lyon"}
    await add_entries_around(entry, "lyon", "anonymous")
    assert entry["run_by"] == {
        "uid": "mgen",
        "slug": "mgen",
        "name": "MGEN Action sanitaire et sociale",
        "label": "MGEN",
        "effector_type": "organisme mutualiste",
        "access": "anonymous",
        "siren": None,
    }
    assert entry["services"] == []


async def test_a_porteur_page_lists_the_services_the_viewer_may_see(graph):
    await seed_named(graph)
    anonymous, administrator = {}, {}
    await add_entries_around(anonymous, "mgen", "anonymous")
    await add_entries_around(administrator, "mgen", "administrator")
    assert [s["uid"] for s in anonymous["services"]] == ["lyon"]
    assert [s["uid"] for s in administrator["services"]] == ["other", "lyon"]  # Annexe, then Établissement


def test_the_full_entry_type_carries_the_porteur_and_the_services():
    from api.types.fullentry import FullEntry, RelatedEntry

    assert {"run_by", "services"} <= set(FullEntry.model_fields)
    item = RelatedEntry.model_validate(
        {"uid": "u", "slug": "s", "name": "N", "label": "L", "effector_type": "T", "access": "anonymous"}
    )
    assert item.model_dump() == {"uid": "u", "slug": "s", "name": "N", "label": "L", "effector_type": "T", "siren": None}
