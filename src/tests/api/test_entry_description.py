"""An entry's description, through the entries API.

The summary a professional reads on the entry page: what the service offers, for
whom, on what terms. It lives on the Entry node, in the site's one language, and is
edited by whoever may edit the entry, through the same PATCH as the facets. Null
removes it, silence keeps it, a blank one is no description, and an overlong one is
refused before anything is written.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from api.serializers.entries import update_entry
from api.types.entry import DESCRIPTION_MAX, Entry, EntryPatch
from api.types.fullentry import FullEntry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ALSM = "Permanences d'écoute gratuites et anonymes, sans rendez-vous, assurées par un psychologue et un acteur de prévention."


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
    rows, _ = await adb.cypher_query("MATCH (e:Entry {uid: 'alsm'}) RETURN e.description")
    return rows[0][0]


async def test_a_description_is_stored_and_returned(graph):
    entry = await patch_entry({"description": ALSM})
    assert entry.description == ALSM
    assert await stored(graph) == ALSM


async def test_null_removes_it_and_silence_keeps_it(graph):
    await patch_entry({"description": ALSM})
    kept = await patch_entry({"free": True})
    assert kept.description == ALSM
    removed = await patch_entry({"description": None})
    assert removed.description is None
    assert await stored(graph) is None


async def test_surrounding_blanks_are_dropped_and_a_blank_description_is_none(graph):
    trimmed = await patch_entry({"description": f"  {ALSM}\n"})
    assert trimmed.description == ALSM
    blank = await patch_entry({"description": " \n "})
    assert blank.description is None
    assert await stored(graph) is None


def test_an_overlong_description_is_refused_before_anything_is_written():
    EntryPatch(description="x" * DESCRIPTION_MAX)
    with pytest.raises(ValidationError):
        EntryPatch(description="x" * (DESCRIPTION_MAX + 1))


def test_the_page_payload_carries_the_description():
    assert "description" in FullEntry.model_fields
    assert "description" in Entry.model_fields
