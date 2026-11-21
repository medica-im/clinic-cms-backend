"""The association endpoints: officers and board members of an entry.

Both read and write the graph with raw Cypher through `adb`, so a result is
`results[0][...]` and an empty one is an empty list, not `[[]]`. These tests
pin the paths that never had one: the empty list, the unknown uid, the caller
with no access to the entry, and a stop date that is cleared rather than left.

`authorize_api` is patched (the AccessControl rows are another test's concern);
`verify_user_access` is real, so the caller's Account, User and Access are
seeded.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SUB = "association-sub-001"


@pytest.fixture
async def graph(neo4j_graph):
    """An entry the caller may edit, a second one they may not, and what the endpoints link to."""
    from neomodel import adb

    uids = {name: uuid.uuid4().hex for name in (
        "entry", "other_entry", "effector", "role", "category", "user", "account", "access",
    )}
    await adb.cypher_query(
        """
        CREATE (e:Entry {uid: $entry}), (o:Entry {uid: $other_entry})
        CREATE (eff:Effector {uid: $effector})
        CREATE (r:OrganizationRole {uid: $role})
        CREATE (c:MembershipCategory {uid: $category})
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
    from contextlib import ExitStack

    jwt = {"providerAccountId": SUB, "sub": SUB, "email": "a@example.com", "name": "A"}
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt))
        stack.enter_context(patch("api.routers.association.authorize_api", AsyncMock(return_value=True)))
        yield


def officer(graph, **over):
    return {
        "entry_uid": graph["entry"], "effector_uid": graph["effector"],
        "role_uid": graph["role"], "role_label": "Présidente", "start": "2024-01-01",
        **over,
    }


def board_member(graph, **over):
    return {
        "entry_uid": graph["entry"], "effector_uid": graph["effector"],
        "category_uid": graph["category"], "start": "2024-01-01", **over,
    }


class TestOfficers:

    async def test_an_entry_without_officers_lists_none(self, client, graph):
        r = await client.get("/officers", params={"entry_uid": graph["entry"]})
        assert r.status_code == 200
        assert r.json() == []

    async def test_an_unknown_entry_lists_none(self, client, graph):
        r = await client.get("/officers", params={"entry_uid": uuid.uuid4().hex})
        assert r.status_code == 200
        assert r.json() == []

    async def test_creating_one_returns_it_and_the_list_shows_it(self, client, graph, signed_in):
        r = await client.post("/officers", json=officer(graph))
        assert r.status_code == 201
        body = r.json()
        assert body["entry_uid"] == graph["entry"]
        assert body["effector_uid"] == graph["effector"]
        assert body["role_uid"] == graph["role"]
        assert body["role_label"] == "Présidente"
        assert body["start"] == "2024-01-01"
        assert body["stop"] is None

        listed = await client.get("/officers", params={"entry_uid": graph["entry"]})
        assert [o["uid"] for o in listed.json()] == [body["uid"]]

    async def test_a_stop_date_is_kept(self, client, graph, signed_in):
        r = await client.post("/officers", json=officer(graph, stop="2025-06-30"))
        assert r.json()["stop"] == "2025-06-30"

    async def test_an_unknown_role_is_not_found(self, client, graph, signed_in):
        r = await client.post("/officers", json=officer(graph, role_uid=uuid.uuid4().hex))
        assert r.status_code == 404

    async def test_an_entry_the_caller_has_no_access_to_is_refused(self, client, graph, signed_in):
        r = await client.post("/officers", json=officer(graph, entry_uid=graph["other_entry"]))
        assert r.status_code == 403

    async def test_creating_without_signing_in_is_refused(self, client, graph):
        r = await client.post("/officers", json=officer(graph))
        assert r.status_code == 401

    async def test_updating_changes_only_what_is_sent(self, client, graph, signed_in):
        created = (await client.post("/officers", json=officer(graph))).json()
        r = await client.patch(f"/officers/{created['uid']}", json={"role_label": "Trésorier"})
        assert r.status_code == 200
        assert r.json()["role_label"] == "Trésorier"
        assert r.json()["start"] == "2024-01-01"

    async def test_a_null_stop_clears_the_date(self, client, graph, signed_in):
        created = (await client.post("/officers", json=officer(graph, stop="2025-06-30"))).json()
        r = await client.patch(f"/officers/{created['uid']}", json={"stop": None})
        assert r.status_code == 200
        assert r.json()["stop"] is None

    async def test_updating_an_unknown_officer_is_not_found(self, client, graph, signed_in):
        r = await client.patch(f"/officers/{uuid.uuid4().hex}", json={"start": "2024-02-01"})
        assert r.status_code == 404

    async def test_updating_an_officer_of_an_entry_without_access_is_refused(self, client, graph, signed_in):
        from neomodel import adb

        uid = uuid.uuid4().hex
        await adb.cypher_query(
            """
            MATCH (o:Entry {uid: $other_entry}), (eff:Effector {uid: $effector}), (r:OrganizationRole {uid: $role})
            CREATE (x:Officer {uid: $uid, start: date('2024-01-01')})
            CREATE (x)-[:MEMBER_OF]->(o), (x)-[:HAS_EFFECTOR]->(eff), (x)-[:HAS_ROLE {label: 'x'}]->(r)
            """,
            {**graph, "uid": uid},
        )
        r = await client.patch(f"/officers/{uid}", json={"start": "2024-02-01"})
        assert r.status_code == 403

    async def test_deleting_removes_it(self, client, graph, signed_in):
        created = (await client.post("/officers", json=officer(graph))).json()
        r = await client.delete(f"/officers/{created['uid']}")
        assert r.status_code == 200
        assert r.json() == {"message": "Officer deleted", "uid": created["uid"]}

        listed = await client.get("/officers", params={"entry_uid": graph["entry"]})
        assert listed.json() == []

    async def test_deleting_leaves_what_it_pointed_to(self, client, graph, signed_in):
        from neomodel import adb

        created = (await client.post("/officers", json=officer(graph))).json()
        await client.delete(f"/officers/{created['uid']}")
        rows, _ = await adb.cypher_query(
            "MATCH (n) WHERE n.uid IN [$entry, $effector, $role] RETURN count(n)", graph
        )
        assert rows[0][0] == 3

    async def test_deleting_an_unknown_officer_is_not_found(self, client, graph, signed_in):
        r = await client.delete(f"/officers/{uuid.uuid4().hex}")
        assert r.status_code == 404


class TestBoardMembers:

    async def test_an_entry_without_board_members_lists_none(self, client, graph):
        r = await client.get("/board-members", params={"entry_uid": graph["entry"]})
        assert r.status_code == 200
        assert r.json() == []

    async def test_creating_one_with_a_category(self, client, graph, signed_in):
        r = await client.post("/board-members", json=board_member(graph))
        assert r.status_code == 201
        body = r.json()
        assert body["category_uid"] == graph["category"]
        assert body["start"] == "2024-01-01"
        assert body["stop"] is None

        listed = await client.get("/board-members", params={"entry_uid": graph["entry"]})
        assert [m["uid"] for m in listed.json()] == [body["uid"]]

    async def test_creating_one_without_a_category(self, client, graph, signed_in):
        r = await client.post("/board-members", json=board_member(graph, category_uid=None))
        assert r.status_code == 201
        assert r.json()["category_uid"] is None

        listed = await client.get("/board-members", params={"entry_uid": graph["entry"]})
        assert [m["category_uid"] for m in listed.json()] == [None]

    async def test_an_unknown_category_is_not_found(self, client, graph, signed_in):
        r = await client.post("/board-members", json=board_member(graph, category_uid=uuid.uuid4().hex))
        assert r.status_code == 404

    async def test_an_unknown_effector_is_not_found(self, client, graph, signed_in):
        r = await client.post("/board-members", json=board_member(graph, effector_uid=uuid.uuid4().hex))
        assert r.status_code == 404

    async def test_an_entry_the_caller_has_no_access_to_is_refused(self, client, graph, signed_in):
        r = await client.post("/board-members", json=board_member(graph, entry_uid=graph["other_entry"]))
        assert r.status_code == 403

    async def test_a_null_stop_clears_the_date(self, client, graph, signed_in):
        created = (await client.post("/board-members", json=board_member(graph, stop="2025-06-30"))).json()
        assert created["stop"] == "2025-06-30"
        r = await client.patch(f"/board-members/{created['uid']}", json={"stop": None})
        assert r.status_code == 200
        assert r.json()["stop"] is None
        assert r.json()["category_uid"] == graph["category"]

    async def test_updating_an_unknown_board_member_is_not_found(self, client, graph, signed_in):
        r = await client.patch(f"/board-members/{uuid.uuid4().hex}", json={"start": "2024-02-01"})
        assert r.status_code == 404

    async def test_deleting_removes_it(self, client, graph, signed_in):
        created = (await client.post("/board-members", json=board_member(graph))).json()
        r = await client.delete(f"/board-members/{created['uid']}")
        assert r.status_code == 200
        assert r.json() == {"message": "BoardMember deleted", "uid": created["uid"]}

        listed = await client.get("/board-members", params={"entry_uid": graph["entry"]})
        assert listed.json() == []

    async def test_deleting_an_unknown_board_member_is_not_found(self, client, graph, signed_in):
        r = await client.delete(f"/board-members/{uuid.uuid4().hex}")
        assert r.status_code == 404
