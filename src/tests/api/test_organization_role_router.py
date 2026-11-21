"""The organization-role endpoints: the roles an association's officers hold.

Raw Cypher through `adb`; an empty result is an empty list, never `[[]]`.
Pinned here: the empty list, the unknown uid, and the delete an officer's link
forbids. The role labels endpoint is test_organization_role_labels's.

`authorize_api` is patched; the AccessControl rows are another test's concern.
"""
import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def signed_in(patch_jwt):
    jwt = {"providerAccountId": "org-role-sub", "sub": "org-role-sub", "email": "a@example.com", "name": "A"}
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt))
        stack.enter_context(patch("api.routers.organization_role.authorize_api", AsyncMock(return_value=True)))
        yield


async def create(client, label="Président"):
    return await client.post("/organization-roles", json={"label": label})


async def test_no_roles_lists_none(client, neo4j_graph, signed_in):
    r = await client.get("/organization-roles")
    assert r.status_code == 200
    assert r.json() == []


async def test_creating_one_returns_it_and_the_list_shows_it(client, neo4j_graph, signed_in):
    r = await create(client)
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "Président"

    listed = await client.get("/organization-roles")
    assert listed.json() == [body]


async def test_listing_without_signing_in_is_refused(client, neo4j_graph):
    r = await client.get("/organization-roles")
    assert r.status_code == 401


async def test_updating_changes_the_label(client, neo4j_graph, signed_in):
    created = (await create(client)).json()
    r = await client.patch(f"/organization-roles/{created['uid']}", json={"label": "Présidente"})
    assert r.status_code == 200
    assert r.json() == {"uid": created["uid"], "label": "Présidente"}


async def test_updating_with_nothing_sent_changes_nothing(client, neo4j_graph, signed_in):
    created = (await create(client)).json()
    r = await client.patch(f"/organization-roles/{created['uid']}", json={})
    assert r.status_code == 200
    assert r.json() == created


async def test_updating_an_unknown_role_is_not_found(client, neo4j_graph, signed_in):
    r = await client.patch(f"/organization-roles/{uuid.uuid4().hex}", json={"label": "x"})
    assert r.status_code == 404


async def test_deleting_removes_it(client, neo4j_graph, signed_in):
    created = (await create(client)).json()
    r = await client.delete(f"/organization-roles/{created['uid']}")
    assert r.status_code == 200
    assert r.json() == {"message": "OrganizationRole deleted", "uid": created["uid"]}

    listed = await client.get("/organization-roles")
    assert listed.json() == []


async def test_deleting_one_an_officer_holds_is_a_conflict(client, neo4j_graph, signed_in):
    from neomodel import adb

    created = (await create(client)).json()
    await adb.cypher_query(
        """
        MATCH (r:OrganizationRole {uid: $uid})
        CREATE (o:Officer {uid: 'officer-1', start: date('2024-01-01')})-[:HAS_ROLE {label: 'x'}]->(r)
        """,
        {"uid": created["uid"]},
    )
    r = await client.delete(f"/organization-roles/{created['uid']}")
    assert r.status_code == 409

    listed = await client.get("/organization-roles")
    assert [role["uid"] for role in listed.json()] == [created["uid"]]


async def test_deleting_an_unknown_role_is_not_found(client, neo4j_graph, signed_in):
    r = await client.delete(f"/organization-roles/{uuid.uuid4().hex}")
    assert r.status_code == 404
