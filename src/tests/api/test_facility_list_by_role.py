"""GET /facilities — which list each role is given.

The list itself is tested against a real graph in
test_staff_facility_list_matches_sites.py. These pin down the routing:

  * staff get the base list (the site's facilities and their own creations);
  * administrators and superusers get the repair list, which adds the
    leftovers of inactive entries and of anyone linked to the organization;
  * a superuser gets the *site's* list by default, like everyone else: the
    whole graph mixed in buried the site's facilities, let an entry be
    attached to another site's practice by mistake, and hid bugs like the
    missing unipa facilities from the one role that tests everything;
  * the whole graph is still one explicit step away for a superuser
    (?scope=all) — creating a new project's organization entry needs it —
    and refused to everyone else.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ORG_ENTRY_UID = "3eb0102947274deb9e01cd5c5517173b"
DIRECTORY = "ipa"
USER_UID = "the-user"


@pytest.fixture
def signed_in():
    """Satisfies the JWT dependency; the role is set per test."""
    from main import app
    from api.auth import JWT

    app.dependency_overrides[JWT] = lambda: {"sub": "test-user"}
    try:
        yield
    finally:
        app.dependency_overrides.pop(JWT, None)


@pytest.fixture
def world():
    """The site, its organization and both list builders, replaced."""
    organization = SimpleNamespace(
        neomodel_uid=SimpleNamespace(hex=ORG_ENTRY_UID),
        directory=SimpleNamespace(name=DIRECTORY),
    )
    Organization = MagicMock()
    Organization.objects.select_related.return_value.aget = AsyncMock(return_value=organization)

    mocks = SimpleNamespace(
        role=AsyncMock(),
        organization_list=AsyncMock(return_value=[]),
        whole_graph=AsyncMock(return_value=[]),
        verify_user_access=AsyncMock(),
    )
    patches = [
        patch("api.routers.facilities.get_site_from_request", new=AsyncMock(return_value="site")),
        patch("api.routers.facilities.get_neo4j_role", new=mocks.role),
        patch("api.routers.facilities.Organization", new=Organization),
        patch("api.routers.facilities.verify_user_access", new=mocks.verify_user_access),
        patch("api.routers.facilities.get_neo4j_user",
              new=AsyncMock(return_value=SimpleNamespace(uid=USER_UID))),
        patch("api.routers.facilities.async_get_organization_facilities", new=mocks.organization_list),
        patch("api.routers.facilities.async_get_facilities", new=mocks.whole_graph),
    ]
    for p in patches:
        p.start()
    try:
        yield mocks
    finally:
        for p in patches:
            p.stop()


async def get_as(client, world, role, query=""):
    world.role.return_value = role
    return await client.get(f"/facilities{query}")


# --- Which list ----------------------------------------------------------------


async def test_staff_get_the_base_list(client, signed_in, world):
    response = await get_as(client, world, "staff")

    assert response.status_code == 200
    world.organization_list.assert_awaited_once_with(
        directory=DIRECTORY, org_entry_uid=ORG_ENTRY_UID, user_uid=USER_UID, repair=False
    )


@pytest.mark.parametrize("role", ["administrator", "superuser"])
async def test_administrators_and_superusers_get_the_repair_list(client, signed_in, world, role):
    response = await get_as(client, world, role)

    assert response.status_code == 200
    world.organization_list.assert_awaited_once_with(
        directory=DIRECTORY, org_entry_uid=ORG_ENTRY_UID, user_uid=USER_UID, repair=True
    )


async def test_a_superuser_gets_the_site_not_the_whole_graph_by_default(client, signed_in, world):
    await get_as(client, world, "superuser")

    world.whole_graph.assert_not_awaited()


# --- The whole graph, on request -------------------------------------------------


async def test_a_superuser_can_ask_for_every_facility(client, signed_in, world):
    response = await get_as(client, world, "superuser", "?scope=all")

    assert response.status_code == 200
    world.whole_graph.assert_awaited_once()
    world.organization_list.assert_not_awaited()


@pytest.mark.parametrize("role", ["staff", "administrator"])
async def test_only_a_superuser_may_ask_for_every_facility(client, signed_in, world, role):
    response = await get_as(client, world, role, "?scope=all")

    assert response.status_code == 403
    world.whole_graph.assert_not_awaited()


# --- Access ----------------------------------------------------------------------


@pytest.mark.parametrize("role", ["registered", "anonymous"])
async def test_below_staff_is_refused(client, signed_in, world, role):
    response = await get_as(client, world, role)

    assert response.status_code == 403
    world.organization_list.assert_not_awaited()


async def test_staff_and_administrators_must_have_access_to_the_organization(client, signed_in, world):
    await get_as(client, world, "administrator")

    world.verify_user_access.assert_awaited_once()


async def test_a_superuser_is_not_checked_against_the_organization(client, signed_in, world):
    """A superuser holds no Access node; checking one would refuse them."""
    await get_as(client, world, "superuser")

    world.verify_user_access.assert_not_awaited()
