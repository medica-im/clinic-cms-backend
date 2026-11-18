"""What an entry manages, through the entries API.

Describing what an entry handles is part of editing it, so whoever may edit the
entry (its owner included) may set it, unlike `run_by`, which publishes a claim on
another entry's page. POST and PATCH go through the same function; a refusal is a
status and a code the page can word, and nothing else of the patch is written.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.serializers.entries import update_entry
from api.types.entry import Entry, EntryPatch, EntryPost
from api.types.fullentry import FullEntry
from directory.manages import get_manages

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (:Entry {uid: 'cmp', active: true, access: 'anonymous'})
        CREATE (:Condition {uid: 'c1', slug: 'addictions'})
        CREATE (:Condition {uid: 'c2', slug: 'troubles-anxieux'})
        """
    )
    return neo4j_graph


def acting_as(role):
    return (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    )


async def patch_entry(body, role="staff"):
    a, b, c = acting_as(role)
    with a, b, c:
        return await update_entry("cmp", EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


@pytest.mark.parametrize("role", ["staff", "administrator", "superuser"])
async def test_whoever_may_edit_the_entry_sets_what_it_manages(graph, role):
    entry = await patch_entry({"manages": ["addictions"]}, role)
    assert entry.manages == ["addictions"]
    assert await get_manages("cmp") == ["addictions"]


async def test_a_patch_replaces_the_list(graph):
    await patch_entry({"manages": ["addictions", "troubles-anxieux"]})
    entry = await patch_entry({"manages": ["troubles-anxieux"]})
    assert entry.manages == ["troubles-anxieux"]
    assert await get_manages("cmp") == ["troubles-anxieux"]


async def test_an_empty_list_clears_it_and_null_is_the_same(graph):
    await patch_entry({"manages": ["addictions"]})
    assert (await patch_entry({"manages": []})).manages == []
    await patch_entry({"manages": ["addictions"]})
    assert (await patch_entry({"manages": None})).manages == []
    assert await get_manages("cmp") == []


async def test_a_patch_that_says_nothing_of_it_leaves_it_alone(graph):
    await patch_entry({"manages": ["addictions"]})
    entry = await patch_entry({"active": True})
    assert entry.manages == ["addictions"]
    assert await get_manages("cmp") == ["addictions"]


async def test_an_unknown_slug_is_a_422_that_names_it_and_writes_nothing_else(graph):
    with pytest.raises(HTTPException) as refused:
        await patch_entry({"manages": ["addictions", "nope"], "active": False})
    assert refused.value.status_code == 422
    assert refused.value.detail == {"code": "unknown_target", "slugs": ["nope"]}
    assert await get_manages("cmp") == []
    rows, _ = await graph.cypher_query("MATCH (e:Entry {uid: 'cmp'}) RETURN e.active")
    assert rows == [[True]]


def test_the_post_body_accepts_it_and_the_default_is_none():
    base = {"effector": "e", "effector_type": "t", "facility": "f", "memberships": None}
    assert EntryPost(**base).manages is None
    assert EntryPost(**base, manages=["addictions"]).manages == ["addictions"]


def test_a_slug_that_is_not_a_slug_is_refused_before_the_graph():
    with pytest.raises(ValueError):
        EntryPatch(manages=["Not A Slug"])


def test_the_payloads_carry_it():
    assert "manages" in Entry.model_fields
    assert "manages" in FullEntry.model_fields
