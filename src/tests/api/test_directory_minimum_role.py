"""Setting a directory's minimum role from the "Annuaires" page.

GET /entries?directory= refuses callers below a sibling directory's
`minimum_role` (test_entries_list_visibility.py). This is where a superuser
sets it: PATCH /directories/{uid}, like the owner switch.

* A site's main directory is public by definition: setting a minimum role
  on it is refused with 409, a rule about the directory, not the caller.
* The sibling lookup is cached for an hour; a change deletes it for every
  directory that can reach this one, so it applies at once.
"""
import pytest
from django.core.cache import cache

from tests.api.test_directory_lists_owner_entry import (  # noqa: F401
    DIRECTORY,
    OTHER_SITE_DIRECTORY,
    SIBLING,
    django_directories,
    graph,
    mock_role,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def main_directory(site, django_directories):  # noqa: F811
    """DIRECTORY is the site's main directory, as Organization.directory says."""
    from directory.models import Directory
    from facility.models import Organization

    main = await Directory.objects.aget(name=DIRECTORY)
    await Organization.objects.acreate(name="Org", site=site, directory=main, active=True)
    return django_directories


async def node_role(name: str):
    from neomodel import adb

    rows, _ = await adb.cypher_query("MATCH (d:Directory {name: $name}) RETURN d.minimum_role", {"name": name})
    return rows[0][0]


async def listed(client) -> dict[str, dict]:
    response = await client.get("/directories")
    assert response.status_code == 200, response.text
    return {d["name"]: d for d in response.json()}


class TestTheListing:
    async def test_it_says_which_directory_is_the_main_one(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            rows = await listed(client)

        assert rows[DIRECTORY]["main"] is True
        assert rows[SIBLING]["main"] is False

    async def test_a_directory_without_a_minimum_role_is_public(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            rows = await listed(client)

        assert rows[SIBLING]["minimum_role"] == "anonymous"


class TestSettingIt:
    async def test_a_superuser_reserves_a_sibling_to_staff(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            response = await client.patch(f"/directories/{main_directory['sibling']}", json={"minimum_role": "staff"})

        assert response.status_code == 200, response.text
        assert response.json()["minimum_role"] == "staff"
        assert await node_role(SIBLING) == "staff"

    async def test_it_leaves_the_owner_switch_alone(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            await client.patch(f"/directories/{main_directory['sibling']}", json={"list_owner_entry": False})
            response = await client.patch(f"/directories/{main_directory['sibling']}", json={"minimum_role": "staff"})

        assert response.json()["list_owner_entry"] is False

    async def test_the_main_directory_stays_public(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            response = await client.patch(f"/directories/{main_directory['dir']}", json={"minimum_role": "staff"})

        assert response.status_code == 409
        assert await node_role(DIRECTORY) is None

    async def test_an_unknown_role_is_refused(self, client, patch_jwt, jwt_superuser, main_directory):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            response = await client.patch(f"/directories/{main_directory['sibling']}", json={"minimum_role": "staf"})

        assert response.status_code == 422

    @pytest.mark.parametrize("role", ["administrator", "staff"])
    async def test_only_a_superuser_may(self, client, patch_jwt, jwt_superuser, main_directory, role):
        with patch_jwt(jwt_superuser), mock_role(role):
            response = await client.patch(f"/directories/{main_directory['sibling']}", json={"minimum_role": "staff"})

        assert response.status_code == 403
        assert await node_role(SIBLING) is None

    async def test_it_applies_at_once(self, client, patch_jwt, jwt_superuser, main_directory):
        """Every directory that can reach this one loses its cached answer."""
        keys = [f"v2:directory-access:{own}:{SIBLING}" for own in (DIRECTORY, SIBLING, OTHER_SITE_DIRECTORY)]
        for key in keys:
            cache.set(key, "anonymous")

        with patch_jwt(jwt_superuser), mock_role("superuser"):
            await client.patch(f"/directories/{main_directory['sibling']}", json={"minimum_role": "staff"})

        assert [cache.get(key) for key in keys] == [None, None, None]
