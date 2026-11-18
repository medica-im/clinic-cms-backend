"""A caller's role comes from their Access in the graph, and from nowhere else.

Django's own notion of a superuser (User.is_superuser, which still governs the
Django admin) is not consulted when authorizing an API request. A second source
of roles lets one undo the other: a user suspended in the graph has no role
there by design, and a role found elsewhere hands it straight back.

`get_neo4j_role` returning None is what a suspended Access looks like, as well
as a user with no Access on the site at all; both are judged as anonymous.
"""
from unittest.mock import MagicMock

import pytest

from api.auth import may_authorize_api

pytestmark = pytest.mark.asyncio

ENDPOINT = "single_source_v2"
EMAIL = "legacy@example.com"
JWT = {"email": EMAIL, "providerAccountId": "legacy-sub"}


@pytest.fixture
def acl(roles):
    from access.models import AccessControl, Endpoint

    endpoint = Endpoint.objects.create(name=ENDPOINT)
    for name, permissions in {
        "superuser": 15, "administrator": 15, "staff": 3, "anonymous": 1,
    }.items():
        AccessControl.objects.create(
            endpoint=endpoint, role=roles[name], permissions=permissions
        )


@pytest.fixture
def django_superuser(site):
    from accounts.models import User

    return User.objects.create_superuser("legacy", EMAIL, "unused")


def _request(method):
    return MagicMock(method=method)


async def test_the_django_superuser_flag_grants_nothing(
    acl, django_superuser, mock_get_site, mock_neo4j_role
):
    with mock_get_site, mock_neo4j_role(None):
        assert not await may_authorize_api(ENDPOINT, _request("DELETE"), JWT)


async def test_a_user_suspended_in_the_graph_gets_nothing_back_from_django(
    acl, django_superuser, mock_get_site, mock_neo4j_role
):
    with mock_get_site, mock_neo4j_role(None):
        assert not await may_authorize_api(ENDPOINT, _request("POST"), JWT)
        assert await may_authorize_api(ENDPOINT, _request("GET"), JWT), (
            "without a role in the graph the caller is anonymous, not locked out"
        )


async def test_the_graph_role_is_the_one_that_counts(
    acl, django_superuser, mock_get_site, mock_neo4j_role
):
    with mock_get_site, mock_neo4j_role("staff"):
        assert await may_authorize_api(ENDPOINT, _request("POST"), JWT)
        assert not await may_authorize_api(ENDPOINT, _request("DELETE"), JWT)
