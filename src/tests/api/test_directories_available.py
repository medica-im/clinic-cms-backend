"""Integration tests for GET /directories/available.

Exercises the real Cypher traversal
    (Directory)-[:OWNED_BY]->(Entry)<-[:OWNED_BY]-(Directory)
against a throwaway Neo4j 4.4 Enterprise container (see conftest_neo4j.py),
backed by a real (ephemeral) Django DB for the Directory rows the serializer
joins on by name.

Auth is mocked (get_neo4j_role) per the endpoint's admin-only gate; the graph
query itself runs for real so the relationship-uniqueness behaviour that made
the current/default directory drop out is locked in by test.

Topology seeded per test (unless a test overrides it):
    Entry(org-a) <-[:OWNED_BY]- Directory(current)   # the site's own directory
    Entry(org-a) <-[:OWNED_BY]- Directory(sibling)   # same owner -> available
    Entry(org-b) <-[:OWNED_BY]- Directory(other)     # different owner -> excluded
"""
import uuid
import pytest
import pytest_asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def mock_role(role_name):
    """Patch get_neo4j_role as imported into the directories router module."""
    with patch(
        "api.routers.directories.get_neo4j_role",
        new_callable=AsyncMock,
        return_value=role_name,
    ):
        yield


async def seed_entry(adb, uid):
    await adb.cypher_query(
        "CREATE (e:Entry {uid: $uid})", {"uid": uid}
    )


async def seed_directory_node(adb, name, owner_uid):
    """Create a :Directory node owned (OWNED_BY) by the given Entry uid."""
    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $owner_uid})
        CREATE (d:Directory {uid: $uid, name: $name})-[:OWNED_BY]->(e)
        """,
        {"uid": uuid.uuid4().hex, "name": name, "owner_uid": owner_uid},
    )


async def make_django_directory(site, name, display_name):
    from directory.models import Directory
    return await Directory.objects.acreate(
        name=name,
        display_name=display_name,
        presentation="",
        site=site,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def topology(neo4j_graph, site, transactional_db):
    """Seed the standard current/sibling/other topology in both DBs.

    Resolves the "current" directory unambiguously via a Postgres Organization
    row (Organization.directory), which async_get_directory_for_site checks
    before falling back to the single-directory-per-site rule.
    """
    from facility.models import Organization

    adb = neo4j_graph
    owner_a = uuid.uuid4().hex
    owner_b = uuid.uuid4().hex
    await seed_entry(adb, owner_a)
    await seed_entry(adb, owner_b)

    # graph nodes
    await seed_directory_node(adb, "current-dir", owner_a)
    await seed_directory_node(adb, "sibling-dir", owner_a)
    await seed_directory_node(adb, "other-dir", owner_b)

    # matching Django rows (serializer joins by name for display_name)
    current = await make_django_directory(site, "current-dir", "Current Directory")
    await make_django_directory(site, "sibling-dir", "Sibling Directory")
    await make_django_directory(site, "other-dir", "Other Directory")

    # pin the site's current directory so resolution is deterministic
    await Organization.objects.acreate(name="Org A", site=site, directory=current)

    return {"owner_a": owner_a, "owner_b": owner_b}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_includes_current_and_sibling_excludes_other(client, patch_jwt, jwt_administrator, topology):
    """Happy path: current + sibling returned, other-owner directory excluded.

    Locks in the fix for the relationship-uniqueness bug: the current/default
    directory MUST appear in the result, not just siblings.
    """
    with patch_jwt(jwt_administrator), mock_role("administrator"):
        resp = await client.get("/directories/available")

    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert names == {"current-dir", "sibling-dir"}
    assert "other-dir" not in names


async def test_current_directory_always_present(client, patch_jwt, jwt_superuser, topology):
    """Even when the owner has only the one directory, it is returned."""
    with patch_jwt(jwt_superuser), mock_role("superuser"):
        resp = await client.get("/directories/available")

    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert "current-dir" in names


async def test_display_name_comes_from_django(client, patch_jwt, jwt_administrator, topology):
    with patch_jwt(jwt_administrator), mock_role("administrator"):
        resp = await client.get("/directories/available")

    by_name = {d["name"]: d["display_name"] for d in resp.json()}
    assert by_name["current-dir"] == "Current Directory"
    assert by_name["sibling-dir"] == "Sibling Directory"


async def test_non_admin_forbidden(client, patch_jwt, jwt_staff, topology):
    with patch_jwt(jwt_staff), mock_role("staff"):
        resp = await client.get("/directories/available")

    assert resp.status_code == 403


async def test_anonymous_unauthorized(client, topology):
    # no JWT override -> the JWT dependency rejects with 401 before the
    # endpoint's role check (403) is ever reached
    resp = await client.get("/directories/available")
    assert resp.status_code == 401


async def test_owner_with_single_directory_returns_only_it(
    client, patch_jwt, jwt_administrator, neo4j_graph, site, transactional_db
):
    """A lone directory (no siblings) returns exactly itself, not []."""
    from facility.models import Organization

    adb = neo4j_graph
    owner = uuid.uuid4().hex
    await seed_entry(adb, owner)
    await seed_directory_node(adb, "solo-dir", owner)
    current = await make_django_directory(site, "solo-dir", "Solo Directory")
    await Organization.objects.acreate(name="Solo Org", site=site, directory=current)

    with patch_jwt(jwt_administrator), mock_role("administrator"):
        resp = await client.get("/directories/available")

    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert names == ["solo-dir"]
