"""GET /api/v2/entry-slugs/{slug}: where a former slug leads now.

The entry page asks it when /fullentries/slug/{slug} answers 404, and
redirects (301) to the current slug. Public, like the entry pages: it maps a
slug that was public to the one that replaced it, and says nothing else.
404 when the slug was never an entry's, or its entry is gone.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

UID = "a" * 32


def lookup(row):
    return patch("api.routers.entry_slugs.former_slug_entry", MagicMock(return_value=row))


def entry(slug):
    nodes = MagicMock(get_or_none=AsyncMock(return_value=SimpleNamespace(uid=UID, slug=slug) if slug else None))
    return patch("api.routers.entry_slugs.AgraphEntry.nodes", nodes)


async def test_a_former_slug_leads_to_the_current_one(versioned_client):
    with lookup(UID), entry("dupont-jean-ipa-69"):
        response = await versioned_client.get("/api/v2/entry-slugs/dupont-jean-mg-69")

    assert response.status_code == 200
    assert response.json() == {"uid": UID, "slug": "dupont-jean-ipa-69"}


async def test_a_slug_that_was_never_an_entrys_is_not_found(versioned_client):
    with lookup(None), entry("unused"):
        response = await versioned_client.get("/api/v2/entry-slugs/nobody-69")

    assert response.status_code == 404


async def test_a_former_slug_of_a_deleted_entry_is_not_found(versioned_client):
    with lookup(UID), entry(None):
        response = await versioned_client.get("/api/v2/entry-slugs/dupont-jean-mg-69")

    assert response.status_code == 404
