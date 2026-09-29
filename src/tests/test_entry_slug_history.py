"""An entry's former slugs keep leading to it.

An entry's slug carries its occupation's abbreviation
(franchino-xavier-mg-69), so changing the occupation gives it a new slug.
The old one has been shared -- links, bookmarks, search results -- so it is
kept in EntrySlug, pointing at the entry's uid, and /e/<old slug> redirects
to the current one.

A former slug is never handed to another entry: the slug generator skips it,
or the redirect would lead to the wrong person.
"""

from unittest.mock import AsyncMock, patch

import pytest
from django.db import IntegrityError

from directory.models import EntrySlug
from directory.slug import _filter_existing_slugs, former_slugs_among

ENTRY_UID = "a" * 32


@pytest.mark.django_db
def test_a_former_slug_points_at_its_entry():
    row = EntrySlug.objects.create(slug="dupont-jean-mg-69", entry_uid=ENTRY_UID, replaced_by="u1")

    assert (row.slug, row.entry_uid, row.replaced_by) == ("dupont-jean-mg-69", ENTRY_UID, "u1")
    assert row.replaced_at is not None


@pytest.mark.django_db
def test_a_former_slug_is_recorded_once():
    EntrySlug.objects.create(slug="dupont-jean-mg-69", entry_uid=ENTRY_UID)

    with pytest.raises(IntegrityError):
        EntrySlug.objects.create(slug="dupont-jean-mg-69", entry_uid="b" * 32)


@pytest.mark.django_db
def test_the_former_slugs_among_candidates_are_found():
    EntrySlug.objects.create(slug="dupont-jean-mg-69", entry_uid=ENTRY_UID)

    assert former_slugs_among(["dupont-jean-mg-69", "dupont-jean-ipa-69"]) == {"dupont-jean-mg-69"}
    assert former_slugs_among([]) == set()


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_the_generator_skips_former_slugs_as_it_skips_current_ones():
    with (
        patch("directory.slug.adb.cypher_query", AsyncMock(return_value=([["taken-now-69"]], None))),
        patch("directory.slug.former_slugs_among", return_value={"taken-before-69"}),
    ):
        free = await _filter_existing_slugs(["taken-now-69", "taken-before-69", "free-69"])

    assert free == ["free-69"]
