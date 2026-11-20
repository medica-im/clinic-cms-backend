"""An organization states the path its pages are served under.

Nginx strips a site's base path before a request reaches the backend, so it is
recorded in Organization.public_base_url ('https://unipa.fr/annuaire') and
published as `base_path` in /api/v2/organization. Another deployment knows a
peer by its origin alone, and its API answers at the root of the domain whatever
the base path: the clone wizard reads this to link to the peer's pages.
"""
import pytest

from api.serializers.organization import base_path_of

from tests.api.test_organization_payload_is_async import (  # noqa: F401
    make_organization,
    organization_entry,
)


@pytest.mark.parametrize("public_base_url, expected", [
    ("", ""),
    ("https://unipa.fr", ""),
    ("https://unipa.fr/", ""),
    ("https://unipa.fr/annuaire", "/annuaire"),
    ("https://unipa.fr/annuaire/", "/annuaire"),
    ("https://example.org/a/b", "/a/b"),
])
def test_the_base_path_is_the_path_of_the_public_url(public_base_url, expected):
    assert base_path_of(public_base_url) == expected


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_organization_payload_carries_its_base_path(organization_entry):  # noqa: F811
    from api.serializers.organization import async_get_django_organization
    from api.types.organization import Organization as OrganizationPy

    org = await make_organization(organization_entry)
    org.public_base_url = "https://unipa.fr/annuaire"
    payload = await async_get_django_organization(org)

    assert OrganizationPy.model_validate(payload).base_path == "/annuaire"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_site_at_its_root_has_an_empty_base_path(organization_entry):  # noqa: F811
    from api.serializers.organization import async_get_django_organization
    from api.types.organization import Organization as OrganizationPy

    org = await make_organization(organization_entry)
    payload = await async_get_django_organization(org)

    assert OrganizationPy.model_validate(payload).base_path == ""
