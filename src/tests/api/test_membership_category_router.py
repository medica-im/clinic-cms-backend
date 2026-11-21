"""The membership-category endpoints: the categories an association's board members belong to.

Raw Cypher through `adb`; an empty result is an empty list, never `[[]]`. Pinned
here: the empty list, the unknown uid, a caller with no access to the entry, and
the delete a board member's link forbids.

`authorize_api` is patched; `verify_user_access` is real, so the caller's
Account, User and Access are seeded.
"""
import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SUB = "membership-category-sub-001"


@pytest.fixture
async def graph(neo4j_graph):
    """An entry the caller may edit and one they may not."""
    from neomodel import adb

    uids = {name: uuid.uuid4().hex for name in (
        "entry", "other_entry", "user", "account", "access", "effector",
    )}
    await adb.cypher_query(
        """
        CREATE (e:Entry {uid: $entry}), (o:Entry {uid: $other_entry})
        CREATE (eff:Effector {uid: $effector})
        CREATE (a:Account {uid: $account, sub: $sub})
        CREATE (u:User {uid: $user})-[:HAS_ACCOUNT]->(a)
        CREATE (u)-[:HAS_ACCESS]->(ac:Access {uid: $access, active: true, role: 'administrator'})
        CREATE (ac)-[:ACCESS_TO]->(e)
        """,
        {**uids, "sub": SUB},
    )
    return uids


@pytest.fixture
def signed_in(patch_jwt):
    jwt = {"providerAccountId": SUB, "sub": SUB, "email": "a@example.com", "name": "A"}
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt))
        stack.enter_context(patch("api.routers.membership_category.authorize_api", AsyncMock(return_value=True)))
        yield


async def create(client, entry_uid, label="Adhérent"):
    return await client.post("/membership-categories", json={"entry_uid": entry_uid, "label": label})


async def other_entrys_category(graph):
    from neomodel import adb

    uid = uuid.uuid4().hex
    await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $other_entry})
        CREATE (:MembershipCategory {uid: $uid, label: 'Ailleurs'})-[:CATEGORY_OF]->(e)
        """,
        {**graph, "uid": uid},
    )
    return uid


async def test_an_entry_without_categories_lists_none(client, graph):
    r = await client.get("/membership-categories", params={"entry_uid": graph["entry"]})
    assert r.status_code == 200
    assert r.json() == []


async def test_creating_one_returns_it_and_the_list_shows_it(client, graph, signed_in):
    r = await create(client, graph["entry"])
    assert r.status_code == 201
    body = r.json()
    assert body["entry_uid"] == graph["entry"]
    assert body["label"] == "Adhérent"

    listed = await client.get("/membership-categories", params={"entry_uid": graph["entry"]})
    assert listed.json() == [body]


async def test_the_list_is_per_entry(client, graph, signed_in):
    await other_entrys_category(graph)
    mine = (await create(client, graph["entry"])).json()

    listed = await client.get("/membership-categories", params={"entry_uid": graph["entry"]})
    assert [c["uid"] for c in listed.json()] == [mine["uid"]]


async def test_creating_for_an_unknown_entry_is_refused(client, graph, signed_in):
    r = await create(client, uuid.uuid4().hex)
    assert r.status_code == 403


async def test_creating_for_an_entry_without_access_is_refused(client, graph, signed_in):
    r = await create(client, graph["other_entry"])
    assert r.status_code == 403


async def test_creating_without_signing_in_is_refused(client, graph):
    r = await create(client, graph["entry"])
    assert r.status_code == 401


async def test_updating_changes_the_label(client, graph, signed_in):
    created = (await create(client, graph["entry"])).json()
    r = await client.patch(f"/membership-categories/{created['uid']}", json={"label": "Bienfaiteur"})
    assert r.status_code == 200
    assert r.json() == {**created, "label": "Bienfaiteur"}


async def test_updating_with_nothing_sent_changes_nothing(client, graph, signed_in):
    created = (await create(client, graph["entry"])).json()
    r = await client.patch(f"/membership-categories/{created['uid']}", json={})
    assert r.status_code == 200
    assert r.json() == created


async def test_updating_an_unknown_category_is_not_found(client, graph, signed_in):
    r = await client.patch(f"/membership-categories/{uuid.uuid4().hex}", json={"label": "x"})
    assert r.status_code == 404


async def test_updating_a_category_of_an_entry_without_access_is_refused(client, graph, signed_in):
    uid = await other_entrys_category(graph)
    r = await client.patch(f"/membership-categories/{uid}", json={"label": "x"})
    assert r.status_code == 403


async def test_deleting_removes_it(client, graph, signed_in):
    created = (await create(client, graph["entry"])).json()
    r = await client.delete(f"/membership-categories/{created['uid']}")
    assert r.status_code == 200
    assert r.json() == {"message": "MembershipCategory deleted", "uid": created["uid"]}

    listed = await client.get("/membership-categories", params={"entry_uid": graph["entry"]})
    assert listed.json() == []


async def test_deleting_one_a_board_member_holds_is_a_conflict(client, graph, signed_in):
    from neomodel import adb

    created = (await create(client, graph["entry"])).json()
    await adb.cypher_query(
        """
        MATCH (mc:MembershipCategory {uid: $uid}), (e:Entry {uid: $entry}), (eff:Effector {uid: $effector})
        CREATE (bm:BoardMember {uid: 'bm-1', start: date('2024-01-01')})
        CREATE (bm)-[:MEMBER_OF]->(e), (bm)-[:HAS_EFFECTOR]->(eff), (bm)-[:HAS_MEMBERSHIP_CATEGORY]->(mc)
        """,
        {**graph, "uid": created["uid"]},
    )
    r = await client.delete(f"/membership-categories/{created['uid']}")
    assert r.status_code == 409

    listed = await client.get("/membership-categories", params={"entry_uid": graph["entry"]})
    assert [c["uid"] for c in listed.json()] == [created["uid"]]


async def test_deleting_an_unknown_category_is_not_found(client, graph, signed_in):
    r = await client.delete(f"/membership-categories/{uuid.uuid4().hex}")
    assert r.status_code == 404
