"""The site's sharing card, /api/v1/opengraph/.

A site without a card is a normal state, not an error: it answers 204 with no
body. A 404 there made every browser log "Failed to load resource" on the home
page of each such site, which the staging reload checks report as a broken page.
"""
import pytest
from django.test import Client


@pytest.fixture
def current_site(site, settings):
    settings.SITE_ID = site.pk
    return site


def test_a_site_without_a_card_answers_204_with_no_body(current_site):
    response = Client().get("/api/v1/opengraph/")
    assert response.status_code == 204
    assert response.content == b""


def test_a_site_with_a_card_still_gets_it(current_site):
    from opengraph.models import TwitterCard

    TwitterCard.objects.create(
        site=current_site, title="Maison de santé", username="@msp", image="opengraph/card.png"
    )
    response = Client().get("/api/v1/opengraph/")
    assert response.status_code == 200
    assert response.json()["title"] == "Maison de santé"


def test_a_card_without_an_image_is_served_without_one(current_site):
    """X's summary card and the frontend both take an image as optional."""
    from opengraph.models import TwitterCard

    TwitterCard.objects.create(site=current_site, title="Maison de santé", username="@msp")
    response = Client().get("/api/v1/opengraph/")
    assert response.status_code == 200
    assert response.json()["title"] == "Maison de santé"
    assert response.json()["image_url"] is None
