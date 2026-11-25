"""The peer registry, kept from outside: GET and PUT /api/v2/clone/peers.

A peer is a trust decision, so the list is not in code and not discovered: the
console holds it as a reviewed file and pushes the whole list to every backend,
each of which has its own registry. PUT makes the registry match that list.

A peer the list no longer names is retired (`active=False`), never deleted: the
row stays for the admin to read and to bring back, which is how the model says
"retire a peer without deleting its row".
"""
import pytest
from asgiref.sync import sync_to_async

from directory.models import PeerInstance

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]

URL = "/api/v2/clone/peers"

UNIPA = {
    "name": "unipa-staging",
    "display_name": "UNIPA (staging)",
    "origin": "https://staging.unipa.fr",
    "outbound": True,
    "inbound": True,
}
PROD = {
    "name": "santelyon3-prod",
    "display_name": "Santé Lyon 3 (production)",
    "origin": "https://santelyon3.fr",
    "outbound": True,
    "inbound": False,
}


@pytest.fixture
def as_superuser(monkeypatch, patch_jwt, jwt_superuser, site):
    from contextlib import contextmanager
    from unittest.mock import AsyncMock

    import api.routers.clone as router_module

    @contextmanager
    def _as(role="superuser"):
        monkeypatch.setattr(router_module, "get_neo4j_role", AsyncMock(return_value=role))
        monkeypatch.setattr(router_module, "get_site_from_request", AsyncMock(return_value=site))
        with patch_jwt(jwt_superuser):
            yield

    return _as


async def rows():
    return {
        p.name: p
        for p in await sync_to_async(list, thread_sensitive=True)(PeerInstance.objects.all())
    }


class TestPut:
    async def test_it_registers_the_peers_it_is_given(self, versioned_client, as_superuser):
        with as_superuser():
            r = await versioned_client.put(URL, json=[UNIPA, PROD])

        assert r.status_code == 200
        registered = await rows()
        assert set(registered) == {"unipa-staging", "santelyon3-prod"}
        assert registered["unipa-staging"].origin == "https://staging.unipa.fr"
        assert registered["unipa-staging"].active is True
        assert (registered["santelyon3-prod"].outbound, registered["santelyon3-prod"].inbound) == (True, False)
        assert r.json() == {"created": ["unipa-staging", "santelyon3-prod"], "updated": [], "retired": []}

    async def test_it_updates_a_peer_that_changed(self, versioned_client, as_superuser):
        with as_superuser():
            await versioned_client.put(URL, json=[UNIPA])
            r = await versioned_client.put(URL, json=[{**UNIPA, "display_name": "UNIPA preprod", "inbound": False}])

        row = (await rows())["unipa-staging"]
        assert (row.display_name, row.inbound) == ("UNIPA preprod", False)
        assert r.json() == {"created": [], "updated": ["unipa-staging"], "retired": []}

    async def test_it_reports_nothing_when_nothing_changed(self, versioned_client, as_superuser):
        with as_superuser():
            await versioned_client.put(URL, json=[UNIPA])
            r = await versioned_client.put(URL, json=[UNIPA])

        assert r.json() == {"created": [], "updated": [], "retired": []}

    async def test_a_peer_left_out_is_retired_not_deleted(self, versioned_client, as_superuser):
        with as_superuser():
            await versioned_client.put(URL, json=[UNIPA, PROD])
            r = await versioned_client.put(URL, json=[UNIPA])

        registered = await rows()
        assert registered["santelyon3-prod"].active is False
        assert registered["unipa-staging"].active is True
        assert r.json()["retired"] == ["santelyon3-prod"]

    async def test_a_retired_peer_named_again_is_active_again(self, versioned_client, as_superuser):
        with as_superuser():
            await versioned_client.put(URL, json=[UNIPA, PROD])
            await versioned_client.put(URL, json=[UNIPA])
            r = await versioned_client.put(URL, json=[UNIPA, PROD])

        assert (await rows())["santelyon3-prod"].active is True
        assert r.json()["updated"] == ["santelyon3-prod"]

    @pytest.mark.parametrize("origin", [
        "http://staging.unipa.fr",
        "https://staging.unipa.fr/annuaire",
        "https://user:pw@staging.unipa.fr",
    ])
    async def test_an_origin_that_is_not_an_https_origin_is_refused(self, versioned_client, as_superuser, origin):
        with as_superuser():
            r = await versioned_client.put(URL, json=[{**UNIPA, "origin": origin}])

        assert r.status_code == 422
        assert await rows() == {}

    async def test_a_refused_list_changes_nothing(self, versioned_client, as_superuser):
        """One bad row must not leave the registry half-applied."""
        with as_superuser():
            await versioned_client.put(URL, json=[PROD])
            r = await versioned_client.put(URL, json=[UNIPA, {**PROD, "origin": "http://santelyon3.fr"}])

        assert r.status_code == 422
        registered = await rows()
        assert set(registered) == {"santelyon3-prod"}
        assert registered["santelyon3-prod"].active is True

    async def test_two_peers_may_not_share_a_name_or_an_origin(self, versioned_client, as_superuser):
        with as_superuser():
            same_name = await versioned_client.put(URL, json=[UNIPA, {**PROD, "name": "unipa-staging"}])
            same_origin = await versioned_client.put(URL, json=[UNIPA, {**PROD, "origin": UNIPA["origin"]}])

        assert same_name.status_code == 422
        assert same_origin.status_code == 422
        assert await rows() == {}


class TestGet:
    async def test_it_lists_every_peer_retired_ones_included(self, versioned_client, as_superuser):
        with as_superuser():
            await versioned_client.put(URL, json=[UNIPA, PROD])
            await versioned_client.put(URL, json=[UNIPA])
            r = await versioned_client.get(URL)

        by_name = {p["name"]: p for p in r.json()}
        assert set(by_name) == {"unipa-staging", "santelyon3-prod"}
        assert by_name["santelyon3-prod"] == {**PROD, "active": False}
        assert by_name["unipa-staging"] == {**UNIPA, "active": True}

    async def test_it_is_empty_before_any_peer(self, versioned_client, as_superuser):
        with as_superuser():
            r = await versioned_client.get(URL)

        assert r.status_code == 200
        assert r.json() == []


class TestWhoMayDoIt:
    @pytest.mark.parametrize("role", ["administrator", "staff", "registered", None])
    @pytest.mark.parametrize("method", ["get", "put"])
    async def test_only_a_superuser(self, versioned_client, as_superuser, role, method):
        """Writing the registry decides which servers may pull this directory's contact data."""
        with as_superuser(role):
            kwargs = {"json": [UNIPA]} if method == "put" else {}
            r = await getattr(versioned_client, method)(URL, **kwargs)

        assert r.status_code == 403
        assert await rows() == {}
