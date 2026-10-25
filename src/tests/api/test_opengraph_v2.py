"""The site's sharing card on FastAPI, /api/v2/opengraph.

204 with no body for a site without a card — a normal state, which a 404 made
every browser log as "Failed to load resource". The answer is cached per site,
the absence of a card included, and saving or deleting a card clears its site's
entry so an edit in the admin shows at once.

The cache is the dev Redis, so each test removes its own key and nothing else.
"""
import pytest
from asgiref.sync import sync_to_async
from django.core.cache import cache

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]

URL = "/api/v2/opengraph"


@pytest.fixture
def card_site(transactional_db, site):
    from opengraph.cache import opengraph_cache_key

    cache.delete(opengraph_cache_key(site.domain))
    yield site
    cache.delete(opengraph_cache_key(site.domain))


def _create_card(site, **fields):
    from opengraph.models import TwitterCard

    return TwitterCard.objects.create(site=site, title="Maison de santé", username="@msp", **fields)


async def test_a_site_without_a_card_answers_204_with_no_body(versioned_client, card_site):
    response = await versioned_client.get(URL)
    assert response.status_code == 204
    assert response.content == b""


async def test_a_site_with_a_card_gets_it(versioned_client, card_site):
    await sync_to_async(_create_card)(card_site, image="opengraph/card.png", image_alt="La façade")
    response = await versioned_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Maison de santé"
    assert body["username"] == "@msp"
    assert body["image_alt"] == "La façade"
    assert body["image_url"] == f"https://{card_site.domain}/media/opengraph/card.png"


async def test_a_card_without_an_image_is_served_without_one(versioned_client, card_site):
    await sync_to_async(_create_card)(card_site)
    body = (await versioned_client.get(URL)).json()
    assert body["title"] == "Maison de santé"
    assert body["image_url"] is None


async def test_an_edited_card_shows_at_once(versioned_client, card_site):
    card = await sync_to_async(_create_card)(card_site)
    assert (await versioned_client.get(URL)).json()["title"] == "Maison de santé"
    card.title = "Maison de santé de Vedène"
    await sync_to_async(card.save)()
    assert (await versioned_client.get(URL)).json()["title"] == "Maison de santé de Vedène"


async def test_a_card_created_after_a_204_shows_at_once(versioned_client, card_site):
    assert (await versioned_client.get(URL)).status_code == 204
    await sync_to_async(_create_card)(card_site)
    assert (await versioned_client.get(URL)).status_code == 200


async def test_a_deleted_card_is_gone_at_once(versioned_client, card_site):
    card = await sync_to_async(_create_card)(card_site)
    assert (await versioned_client.get(URL)).status_code == 200
    await sync_to_async(card.delete)()
    assert (await versioned_client.get(URL)).status_code == 204
