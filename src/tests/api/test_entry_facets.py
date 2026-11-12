"""Who an entry is for and how to reach it, through the entries API.

Unlike run_by or the SIREN these are not claims about identity: whoever may edit
the entry (its owner, an administrator) describes its public, so no role check
beyond the one PATCH already has. What is pinned here is that the facets are
stored and returned, that sending null removes one and silence keeps it, that a
typo or a reversed age range is refused before anything is written, and that the
page payload carries them.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.serializers.entries import update_entry
from api.types.entry import Entry, EntryPatch, EntryPost
from api.types.fullentry import FullEntry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

FACETS = ("age_min", "age_max", "care_levels", "who_can_contact", "access_modes", "audiences", "free", "anonymous_care")


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query("CREATE (:Entry {uid: 'lyon', active: true, access: 'anonymous'})")
    return neo4j_graph


async def patch_entry(uid, body, role="staff"):
    with (
        patch("api.serializers.entries.get_neo4j_role", AsyncMock(return_value=role)),
        patch("api.serializers.entries.get_site_from_request", AsyncMock(return_value=SimpleNamespace())),
        patch("api.serializers.entries.clear_cache", AsyncMock()),
    ):
        return await update_entry(uid, EntryPatch(**body), SimpleNamespace(), {"sub": "someone"})


async def stored(adb):
    rows, _ = await adb.cypher_query(
        "MATCH (e:Entry {uid: 'lyon'}) RETURN " + ", ".join(f"e.{facet}" for facet in FACETS)
    )
    return dict(zip(FACETS, rows[0]))


async def test_the_lyon_hospital_day_is_for_sixteen_and_up(graph):
    entry = await patch_entry("lyon", {"age_min": 16})
    assert (entry.age_min, entry.age_max) == (16, None)
    assert (await stored(graph))["age_min"] == 16


async def test_every_facet_is_stored_and_returned(graph):
    body = {
        "age_min": 12,
        "age_max": 25,
        "care_levels": ["primary", "emergency"],
        "who_can_contact": "referral",
        "access_modes": ["online", "phone"],
        "audiences": ["students"],
        "free": True,
        "anonymous_care": False,
    }
    entry = await patch_entry("lyon", body)
    expected = {**body, "care_levels": ["emergency", "primary"], "access_modes": ["phone", "online"]}
    assert {facet: getattr(entry, facet) for facet in FACETS} == expected
    assert await stored(graph) == expected


async def test_an_entry_that_says_nothing_has_every_facet_unknown(graph):
    entry = await patch_entry("lyon", {"active": True})
    assert {facet: getattr(entry, facet) for facet in FACETS} == dict.fromkeys(FACETS)


async def test_null_removes_a_facet_and_silence_keeps_the_others(graph):
    await patch_entry("lyon", {"age_min": 16, "who_can_contact": "anyone"})
    kept = await patch_entry("lyon", {"active": True})
    assert (kept.age_min, kept.who_can_contact) == (16, "anyone")
    removed = await patch_entry("lyon", {"age_min": None})
    assert (removed.age_min, removed.who_can_contact) == (None, "anyone")
    assert (await stored(graph))["age_min"] is None


async def test_a_staff_owner_may_describe_the_public_of_an_entry(graph):
    entry = await patch_entry("lyon", {"age_min": 18}, role="staff")
    assert entry.age_min == 18


@pytest.mark.parametrize(
    "body",
    [
        {"who_can_contact": "sur adressage"},
        {"care_levels": ["emergency", "quaternary"]},
        {"access_modes": ["fax"]},
        {"audiences": ["everybody"]},
        {"age_min": -1},
        {"age_max": 200},
        {"age_min": 30, "age_max": 20},
    ],
)
def test_a_typo_or_an_impossible_age_is_refused_before_anything_is_written(body):
    with pytest.raises(ValidationError):
        EntryPatch(**body)


async def test_a_new_bound_that_reverses_the_stored_range_is_a_422_and_changes_nothing(graph):
    await patch_entry("lyon", {"age_min": 16, "age_max": 25})
    with pytest.raises(HTTPException) as refused:
        await patch_entry("lyon", {"age_max": 12, "free": True})
    assert refused.value.status_code == 422
    assert refused.value.detail == {"code": "age_range"}
    after = await stored(graph)
    assert (after["age_min"], after["age_max"], after["free"]) == (16, 25, None)


def test_the_post_body_accepts_the_facets_and_the_default_is_unknown():
    base = {"effector": "e", "effector_type": "t", "facility": "f", "memberships": None}
    assert EntryPost(**base).age_min is None
    assert EntryPost(**base, age_min=16, who_can_contact="anyone").age_min == 16


def test_the_page_payload_carries_the_facets():
    assert set(FACETS) <= set(FullEntry.model_fields)
    assert set(FACETS) <= set(Entry.model_fields)
