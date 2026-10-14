"""Who sees which entries in GET /api/v2/entries.

Three rules, all decided in get_all_entries:

* **Inactive entries.** Anonymous callers never get them: the list is embedded
  in every page of a site, so an inactive entry there is public. Every other
  role gets them. The list is the hot path (every page view, staff included),
  so it stays one payload per role, computed once and cached: no per-person
  filtering, and an entry staff saw while it was active may stay in theirs.
* **?directory=** reaches the site's own directory or a sibling owned by the
  same organization (the rule of /directories/available), nothing else: any
  directory on the backend used to be readable through any site, retired ones
  included. An unknown name is a 404, not a 500.
* **A directory's minimum role** (`minimum_role` on its Neo4j node, absent
  meaning anonymous) refuses lesser callers with a 403. It applies to a
  sibling reached by ?directory=; a site's own directory is public by
  definition, and the default path looks nothing up. CPTS Lyon 3's mental
  health directory is for staff; the page said so, the API did not. The
  sibling lookup is cached like the entries.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from django.core.cache import cache

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ME = uuid.uuid4().hex
SOMEONE = uuid.uuid4().hex


def entry(name: str, active: bool, owner: str | None = None, creator: str | None = None) -> dict:
    return {
        "uid": name,
        "active": active,
        "owner": [owner] if owner else None,
        "creator": [creator] if creator else None,
        "access": "anonymous",
        "name": name,
        "slug": name,
        "effector_uid": f"effector-{name}",
        "address": {"facility_uid": "facility"},
        "commune": {"uid": "commune", "name": "Lyon", "slug": "lyon"},
        "department": {"code": "69"},
        "facility": {"uid": "facility"},
        "effector_type": {"uid": "type", "label": "médecin", "name": "médecin", "slug": "medecin"},
    }


OWN_ENTRIES = [
    entry("active", True, owner=SOMEONE),
    entry("mine-inactive", False, owner=ME),
    entry("created-by-me-inactive", False, creator=ME),
    entry("theirs-inactive", False, owner=SOMEONE, creator=SOMEONE),
]
SIBLING_ENTRIES = [entry("sibling-active", True), entry("sibling-inactive", False)]


@pytest.fixture
async def world(neo4j_graph, site, transactional_db):
    """The site's directory, a sibling, a staff-only sibling, and another
    organization's directory on another site. Names are unique per test: the
    cache is the dev Redis, keyed by directory name."""
    from django.contrib.sites.models import Site

    from directory.models import Directory
    from facility.models import Organization

    suffix = uuid.uuid4().hex[:8]
    names = {k: f"{k}-{suffix}" for k in ("own", "sibling", "staffonly", "other")}
    owner, other_owner = uuid.uuid4().hex, uuid.uuid4().hex
    await neo4j_graph.cypher_query(
        """
        CREATE (o:Entry {uid: $owner}), (x:Entry {uid: $other_owner})
        CREATE (:Directory {uid: randomUUID(), name: $own})-[:OWNED_BY]->(o)
        CREATE (:Directory {uid: randomUUID(), name: $sibling})-[:OWNED_BY]->(o)
        CREATE (:Directory {uid: randomUUID(), name: $staffonly, minimum_role: 'staff'})-[:OWNED_BY]->(o)
        CREATE (:Directory {uid: randomUUID(), name: $other})-[:OWNED_BY]->(x)
        """,
        {"owner": owner, "other_owner": other_owner, **names},
    )
    elsewhere, _ = await Site.objects.aget_or_create(domain="elsewhere.test", defaults={"name": "Elsewhere"})
    rows = {}
    for key, name in names.items():
        rows[key] = await Directory.objects.acreate(
            name=name, display_name=name, presentation="", site=elsewhere if key == "other" else site
        )
    await Organization.objects.acreate(name=f"Org {suffix}", site=site, directory=rows["own"])

    payloads = {
        names["own"]: OWN_ENTRIES,
        names["sibling"]: SIBLING_ENTRIES,
        names["staffonly"]: SIBLING_ENTRIES,
        names["other"]: SIBLING_ENTRIES,
    }

    async def object_list(request, directory_name=None):
        return [dict(e) for e in payloads[directory_name or names["own"]]]

    with patch("api.serializers.allentries.get_object_list", object_list), patch(
        "api.routers.allentries.authorize_api", AsyncMock(return_value=True)
    ):
        yield names


@pytest.fixture
def as_role(versioned_client, patch_jwt):
    """GET /entries as a role; signed-in callers are the user ME."""

    async def _get(role: str, directory: str | None = None):
        url = "/api/v2/entries" + (f"?directory={directory}" if directory else "")
        jwt = None if role == "anonymous" else {"providerAccountId": "me", "email": ""}
        with patch_jwt(jwt), patch(
            "api.serializers.allentries.get_neo4j_role", AsyncMock(return_value=None if role == "anonymous" else role)
        ):
            return await versioned_client.get(url)

    return _get


def uids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {e["uid"] for e in response.json()}


class TestInactiveEntries:
    async def test_an_anonymous_caller_gets_none(self, world, as_role):
        assert uids(await as_role("anonymous")) == {"active"}

    @pytest.mark.parametrize("role", ["staff", "administrator", "superuser"])
    async def test_every_other_role_gets_them_all(self, world, as_role, role):
        assert uids(await as_role(role)) == {e["uid"] for e in OWN_ENTRIES}

    async def test_the_anonymous_cache_holds_none(self, world, as_role):
        await as_role("anonymous")

        cached = cache.get(f"v2:entries:testserver:{world['own']}:anonymous")
        assert cached is not None
        assert [e["uid"] for e in cached] == ["active"]

    async def test_a_sibling_reached_by_name_follows_the_same_rule(self, world, as_role):
        assert uids(await as_role("anonymous", world["sibling"])) == {"sibling-active"}


class TestTheDirectoryParameter:
    async def test_the_site_s_own_directory_by_name(self, world, as_role):
        assert uids(await as_role("anonymous", world["own"])) == {"active"}

    async def test_a_sibling_is_served(self, world, as_role):
        assert (await as_role("anonymous", world["sibling"])).status_code == 200

    @pytest.mark.parametrize("role", ["anonymous", "administrator", "superuser"])
    async def test_another_organization_s_directory_is_not_found(self, world, as_role, role):
        assert (await as_role(role, world["other"])).status_code == 404

    async def test_an_unknown_name_is_not_found(self, world, as_role):
        assert (await as_role("anonymous", f"no-such-{uuid.uuid4().hex}")).status_code == 404


class TestTheMinimumRole:
    async def test_a_staff_directory_refuses_an_anonymous_caller(self, world, as_role):
        assert (await as_role("anonymous", world["staffonly"])).status_code == 403

    @pytest.mark.parametrize("role", ["staff", "administrator", "superuser"])
    async def test_a_staff_directory_serves_staff_and_above(self, world, as_role, role):
        assert (await as_role(role, world["staffonly"])).status_code == 200

    async def test_the_site_s_own_directory_is_public_and_costs_no_lookup(self, world, as_role):
        """A site's own directory is public by definition: the default path,
        every page view's, asks the graph nothing about it."""
        from neomodel import adb

        queries: list[str] = []
        real = adb.cypher_query

        async def spy(query, *args, **kwargs):
            queries.append(query)
            return await real(query, *args, **kwargs)

        with patch.object(adb, "cypher_query", spy):
            response = await as_role("anonymous")

        assert response.status_code == 200
        assert queries == []


class TestTheDirectoryLookupIsCached:
    async def test_a_second_request_does_not_ask_the_graph_again(self, world, as_role):
        from neomodel import adb

        real = adb.cypher_query
        queries: list[str] = []

        async def spy(query, *args, **kwargs):
            queries.append(query)
            return await real(query, *args, **kwargs)

        with patch.object(adb, "cypher_query", spy):
            await as_role("anonymous", world["sibling"])
            first = len(queries)
            await as_role("anonymous", world["sibling"])

        assert first > 0
        assert len(queries) == first


class TestTheModels:
    @pytest.mark.parametrize("module", ["directory.models.graph", "directory.models.agraph"])
    def test_both_directory_models_declare_the_minimum_role(self, module):
        import importlib

        from api.serializers.allentries import ROLE_RANK

        prop = importlib.import_module(module).Directory.defined_properties(rels=False)["minimum_role"]

        assert prop.default == "anonymous"
        assert set(prop.choices) == set(ROLE_RANK)
