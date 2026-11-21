"""An entry's memberships, owners and directories are rewritten to match a list.

Each `update_entry_*` returns whether it changed anything, which the caller uses
to decide whether to clear the caches. The memberships and directories go
through raw Cypher (MERGE / DELETE of one edge), the owners through neomodel's
relationship manager. A uid that names nothing is skipped, not an error.
"""
import uuid
from types import SimpleNamespace

import pytest
from neomodel import adb

from access.asyncneomodels import User as AsyncUser
from api.serializers.entries import (
    connect_member_of,
    unknown_memberships,
    update_entry_directories,
    update_entry_memberships,
    update_entry_owners,
)
from directory.models.agraph import Entry as AsyncEntry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def new_uid():
    return uuid.uuid4().hex


@pytest.fixture
async def graph(neo4j_graph):
    uids = {name: new_uid() for name in ("entry", "a", "b", "c", "u1", "u2", "u3", "org")}
    await adb.cypher_query(
        """
        CREATE (:Entry {uid: $entry}), (:Entry {uid: $a}), (:Entry {uid: $b}), (:Entry {uid: $c})
        CREATE (:User {uid: $u1}), (:User {uid: $u2}), (:User {uid: $u3})
        CREATE (:Organization {uid: $org})
        CREATE (:Directory {name: 'd1'}), (:Directory {name: 'd2'}), (:Directory {name: 'd3'})
        """,
        uids,
    )
    uids["node"] = await AsyncEntry.nodes.get(uid=uids["entry"])
    return uids


async def member_of(entry_uid):
    rows, _ = await adb.cypher_query(
        "MATCH (:Entry {uid: $uid})-[:MEMBER_OF]->(t) RETURN t.uid", {"uid": entry_uid}
    )
    return {row[0] for row in rows}


async def directories_of(entry_uid):
    rows, _ = await adb.cypher_query(
        "MATCH (d:Directory)-[:HAS_ENTRY]->(:Entry {uid: $uid}) RETURN d.name", {"uid": entry_uid}
    )
    return {row[0] for row in rows}


async def owners_of(entry):
    return {u.uid for u in await entry.owner.all()}


class TestMemberships:

    async def test_none_changes_nothing(self, graph):
        assert await update_entry_memberships(graph["node"], None) is False

    async def test_an_empty_list_disconnects_all(self, graph):
        await update_entry_memberships(graph["node"], [graph["a"], graph["b"]])
        assert await update_entry_memberships(graph["node"], []) is True
        assert await member_of(graph["entry"]) == set()

    async def test_connecting_the_first_ones(self, graph):
        assert await update_entry_memberships(graph["node"], [graph["a"], graph["b"]]) is True
        assert await member_of(graph["entry"]) == {graph["a"], graph["b"]}

    async def test_the_same_set_changes_nothing(self, graph):
        await update_entry_memberships(graph["node"], [graph["a"], graph["b"]])
        assert await update_entry_memberships(graph["node"], [graph["b"], graph["a"]]) is False

    async def test_it_adds_what_is_missing_and_drops_what_is_not_listed(self, graph):
        await update_entry_memberships(graph["node"], [graph["a"], graph["b"]])
        assert await update_entry_memberships(graph["node"], [graph["b"], graph["c"]]) is True
        assert await member_of(graph["entry"]) == {graph["b"], graph["c"]}

    async def test_a_uid_that_names_no_entry_is_skipped(self, graph):
        assert await update_entry_memberships(graph["node"], [graph["a"], new_uid()]) is True
        assert await member_of(graph["entry"]) == {graph["a"]}

    async def test_repeating_a_connection_leaves_one_edge(self, graph):
        for _ in range(2):
            await update_entry_memberships(graph["node"], [graph["a"]])
            await update_entry_memberships(graph["node"], [graph["a"], graph["b"]])
            await update_entry_memberships(graph["node"], [graph["a"]])
        rows, _ = await adb.cypher_query(
            "MATCH (:Entry {uid: $e})-[r:MEMBER_OF]->(:Entry {uid: $a}) RETURN count(r)",
            {"e": graph["entry"], "a": graph["a"]},
        )
        assert rows[0][0] == 1


class TestDirectories:

    async def test_none_changes_nothing(self, graph):
        assert await update_entry_directories(graph["node"], None) is False

    async def test_an_entry_in_no_directory_and_an_empty_list_is_unchanged(self, graph):
        assert await update_entry_directories(graph["node"], []) is False

    async def test_connecting_directories(self, graph):
        assert await update_entry_directories(graph["node"], ["d1", "d2"]) is True
        assert await directories_of(graph["entry"]) == {"d1", "d2"}

    async def test_the_same_set_changes_nothing(self, graph):
        await update_entry_directories(graph["node"], ["d1", "d2"])
        assert await update_entry_directories(graph["node"], ["d2", "d1"]) is False

    async def test_an_empty_list_removes_the_entry_from_every_directory(self, graph):
        await update_entry_directories(graph["node"], ["d1", "d2"])
        assert await update_entry_directories(graph["node"], []) is True
        assert await directories_of(graph["entry"]) == set()

    async def test_it_swaps_one_directory_for_another(self, graph):
        await update_entry_directories(graph["node"], ["d1", "d2"])
        assert await update_entry_directories(graph["node"], ["d2", "d3"]) is True
        assert await directories_of(graph["entry"]) == {"d2", "d3"}

    async def test_a_name_that_names_no_directory_is_skipped(self, graph):
        assert await update_entry_directories(graph["node"], ["d1", "nowhere"]) is True
        assert await directories_of(graph["entry"]) == {"d1"}

    async def test_other_entries_keep_their_directories(self, graph):
        await adb.cypher_query(
            "MATCH (d:Directory {name: 'd1'}), (e:Entry {uid: $a}) MERGE (d)-[:HAS_ENTRY]->(e)",
            {"a": graph["a"]},
        )
        await update_entry_directories(graph["node"], ["d1"])
        await update_entry_directories(graph["node"], [])
        assert await directories_of(graph["a"]) == {"d1"}


class TestOwners:

    async def test_none_changes_nothing(self, graph):
        assert await update_entry_owners(graph["node"], None) is False

    async def test_connecting_owners(self, graph):
        assert await update_entry_owners(graph["node"], [graph["u1"], graph["u2"]]) is True
        assert await owners_of(graph["node"]) == {graph["u1"], graph["u2"]}

    async def test_the_same_set_changes_nothing(self, graph):
        await update_entry_owners(graph["node"], [graph["u1"], graph["u2"]])
        assert await update_entry_owners(graph["node"], [graph["u2"], graph["u1"]]) is False

    async def test_it_swaps_one_owner_for_another(self, graph):
        await update_entry_owners(graph["node"], [graph["u1"], graph["u2"]])
        assert await update_entry_owners(graph["node"], [graph["u2"], graph["u3"]]) is True
        assert await owners_of(graph["node"]) == {graph["u2"], graph["u3"]}

    async def test_an_empty_list_removes_every_owner(self, graph):
        await update_entry_owners(graph["node"], [graph["u1"]])
        assert await update_entry_owners(graph["node"], []) is True
        assert await owners_of(graph["node"]) == set()

    async def test_a_uid_that_names_no_user_is_skipped(self, graph):
        assert await update_entry_owners(graph["node"], [graph["u1"], new_uid()]) is True
        assert await owners_of(graph["node"]) == {graph["u1"]}


class TestConnectingAFreshEntry:

    def post(self, memberships):
        return SimpleNamespace(memberships=memberships)

    async def test_an_organization_is_connected_through_the_model(self, graph):
        await connect_member_of(graph["node"], self.post([graph["org"]]))
        assert await member_of(graph["entry"]) == {graph["org"]}

    async def test_an_entry_is_connected_when_the_uid_is_not_an_organization(self, graph):
        await connect_member_of(graph["node"], self.post([graph["a"]]))
        assert await member_of(graph["entry"]) == {graph["a"]}

    async def test_empty_uids_and_no_memberships_do_nothing(self, graph):
        await connect_member_of(graph["node"], self.post(["", None]))
        await connect_member_of(graph["node"], self.post(None))
        assert await member_of(graph["entry"]) == set()

    async def test_a_uid_that_names_nothing_connects_nothing_and_raises_nothing(self, graph):
        """The MERGE's MATCH finds no row and Neo4j reports no failure, so this never raises:
        create_entry refuses the uid beforehand (unknown_memberships)."""
        await connect_member_of(graph["node"], self.post([new_uid()]))
        assert await member_of(graph["entry"]) == set()


class TestRefusingUnknownMemberships:

    async def test_every_known_uid_is_accepted(self, graph):
        assert await unknown_memberships([graph["a"], graph["org"]]) == []

    async def test_the_unknown_ones_are_named_in_the_order_given(self, graph):
        first, second = new_uid(), new_uid()
        assert await unknown_memberships([first, graph["a"], second]) == [first, second]

    async def test_empty_uids_and_repeats_are_ignored(self, graph):
        assert await unknown_memberships(["", graph["a"], graph["a"]]) == []

    async def test_an_empty_list_names_nothing(self, graph):
        assert await unknown_memberships([]) == []
