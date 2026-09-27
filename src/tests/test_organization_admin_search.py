"""Searching the organization list in the Django admin.

The search box crashed on every query (FieldError: "Unsupported lookup
'icontains' for ForeignKey"): search_fields named `city`, a ForeignKey, where
a text field of the related model is needed.

And it could not find an organization by the names people actually use: unipa
is "Union Nationale des Infirmiers en Pratique Avancée" in name and
formatted_name, "UNIPA" only in formatted_name_short, and "unipa" in its
site's domain. An administrator looking for it typed "unipa" (27 Sep 2026).
"""

import pytest
from django.contrib.sites.models import Site

from facility.models import Organization

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/facility/organization/"


@pytest.fixture
def admin_client(client, django_user_model):
    """pytest-django's own admin_client cannot build this project's User:
    its manager's create_superuser also requires a username.

    The Site row is for the test client's host: settings set no SITE_ID, so
    every request looks its Site up by hostname, and "testserver" has none.
    """
    Site.objects.get_or_create(domain="testserver", defaults={"name": "testserver"})
    admin = django_user_model.objects.create_superuser(
        username="search-admin", email="search-admin@example.org", password="x"
    )
    client.force_login(admin)
    return client


@pytest.fixture
def unipa():
    site = Site.objects.create(domain="annuaire.unipa.test", name="unipa")
    return Organization.objects.create(
        name="Union Nationale des Infirmiers en Pratique Avancée",
        formatted_name="Union Nationale des Infirmiers en Pratique Avancée",
        formatted_name_short="UNIPA",
        site=site,
    )


@pytest.fixture
def other():
    return Organization.objects.create(name="CPTS Lyon 3ème", formatted_name="CPTS Lyon 3ème")


def _found(admin_client, query: str) -> list[str]:
    response = admin_client.get(CHANGELIST, {"q": query})
    assert response.status_code == 200
    return [org.name for org in response.context["cl"].result_list]


def test_searching_does_not_crash(admin_client, unipa, other):
    assert admin_client.get(CHANGELIST, {"q": "anything"}).status_code == 200


def test_an_organization_is_found_by_its_short_name(admin_client, unipa, other):
    assert _found(admin_client, "UNIPA") == [unipa.name]


def test_an_organization_is_found_by_its_site_domain(admin_client, unipa, other):
    unipa.formatted_name_short = ""
    unipa.save()

    assert _found(admin_client, "unipa.test") == [unipa.name]


def test_an_organization_is_still_found_by_its_name(admin_client, unipa, other):
    assert _found(admin_client, "Lyon") == [other.name]
