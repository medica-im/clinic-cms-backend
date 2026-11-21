"""create_entry: what it writes, and what it refuses before writing.

An entry is a person (Effector) in an occupation (EffectorType) at a place
(Facility), listed in a directory. Creating one links the three, stamps a slug,
joins the directory, may link a creator and an owner and the organizations it
belongs to, adds the Django Contact, and clears the caches. Calls it makes into
other modules that have their own tests are stubbed: the role, the site, the
directory of the host name, the final FullEntry (which would need the whole
graph around an entry) and the cache clear, which is asserted on.
"""
import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from neomodel import adb

from api.types.entry import EntryPost

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "create-entry-dir"


def new_uid():
    return uuid.uuid4().hex


@pytest.fixture
async def graph(neo4j_graph, transactional_db, roles):
    """A directory, a facility in a commune, a person, an occupation, a user and an organization."""
    uids = {name: new_uid() for name in (
        "commune", "facility", "effector", "type", "hcw_type", "user", "other_user", "org", "other_entry",
    )}
    await adb.cypher_query(
        """
        CREATE (:Directory {name: $directory})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: $commune, name_fr: 'Lyon'})
        CREATE (:Facility {uid: $facility, zip: '69003', street: '1 rue Test'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (:Effector {uid: $effector, name_fr: 'Dr Test', label_fr: 'Dr Test', slug_fr: 'dr-test', gender: 'F'})
        CREATE (:EffectorType {uid: $type, name_fr: 'Coordinateur', label_fr: 'Coordinateur'})
        CREATE (:EffectorType:HCW {uid: $hcw_type, name_fr: 'Infirmier', label_fr: 'Infirmier'})
        CREATE (:User {uid: $user}), (:User {uid: $other_user})
        CREATE (:Organization {uid: $org}), (:Entry {uid: $other_entry})
        """,
        {**uids, "directory": DIRECTORY},
    )
    return uids


@pytest.fixture
def stubs(graph):
    """Everything create_entry asks of the request, the site and the cache; yields the mocks."""
    from directory.models.agraph import Entry

    full = AsyncMock(side_effect=lambda uid, request, jwt: SimpleNamespace(uid=uid))
    clear = AsyncMock()
    state = SimpleNamespace(role="administrator", user=None, full=full, clear=clear)
    with ExitStack() as stack:
        stack.enter_context(patch("api.serializers.entries.get_site_from_request", AsyncMock()))
        stack.enter_context(patch("api.serializers.entries.get_neo4j_role", AsyncMock(side_effect=lambda *a: state.role)))
        stack.enter_context(patch(
            "api.serializers.entries.get_directory_from_hostname",
            AsyncMock(return_value=SimpleNamespace(name=DIRECTORY)),
        ))
        stack.enter_context(patch("api.serializers.entries.get_neo4j_user", AsyncMock(side_effect=lambda jwt: state.user)))
        stack.enter_context(patch("api.serializers.entries.async_get_fullentry", full))
        stack.enter_context(patch("api.serializers.entries.clear_cache", clear))
        yield state


def request():
    return SimpleNamespace(url=SimpleNamespace(hostname="testserver"))


def post(graph, **over):
    return EntryPost(**{
        "effector": graph["effector"], "effector_type": graph["type"], "facility": graph["facility"],
        "memberships": None, **over,
    })


async def create(graph, **over):
    from api.serializers.entries import create_entry

    return await create_entry(post(graph, **over), request(), {"sub": "x"})


async def entries():
    rows, _ = await adb.cypher_query("MATCH (e:Entry) WHERE e.uid <> 'x' RETURN e.uid, e.active, e.slug, e.access")
    return rows


async def links(entry_uid):
    rows, _ = await adb.cypher_query(
        "MATCH (:Entry {uid: $uid})-[r]->(t) RETURN type(r), t.uid", {"uid": entry_uid}
    )
    return {(row[0], row[1]) for row in rows}


async def new_entries(graph):
    return [r for r in await entries() if r[0] != graph["other_entry"]]


class TestWhatItWrites:

    async def test_the_entry_is_linked_to_its_person_occupation_and_place(self, graph, stubs):
        result = await create(graph)
        [(uid, active, slug, access)] = await new_entries(graph)
        assert result.uid == uid
        assert {("HAS_EFFECTOR", graph["effector"]), ("HAS_EFFECTOR_TYPE", graph["type"]),
                ("HAS_FACILITY", graph["facility"])} <= await links(uid)
        assert active is True
        assert access == "anonymous"

    async def test_it_has_a_slug(self, graph, stubs):
        await create(graph)
        [(_, _, slug, _)] = await new_entries(graph)
        assert slug

    async def test_it_joins_the_directory(self, graph, stubs):
        await create(graph)
        [(uid, *_)] = await new_entries(graph)
        rows, _ = await adb.cypher_query(
            "MATCH (:Directory {name: $name})-[:HAS_ENTRY]->(:Entry {uid: $uid}) RETURN count(*)",
            {"name": DIRECTORY, "uid": uid},
        )
        assert rows[0][0] == 1

    async def test_it_gets_a_contact_row(self, graph, stubs):
        from addressbook.models import Contact

        await create(graph)
        [(uid, *_)] = await new_entries(graph)
        assert await Contact.objects.filter(neomodel_uid=uid).aexists()

    async def test_the_entries_cache_is_cleared(self, graph, stubs):
        await create(graph)
        stubs.clear.assert_awaited_once()
        assert stubs.clear.await_args.args[0] == "v2:entries"

    async def test_it_answers_with_the_full_entry(self, graph, stubs):
        result = await create(graph)
        [(uid, *_)] = await new_entries(graph)
        assert result.uid == uid
        assert stubs.full.await_args.args[0] == uid

    async def test_the_access_it_was_given_is_kept(self, graph, stubs):
        await create(graph, access="registered")
        [(_, _, _, access)] = await new_entries(graph)
        assert access == "registered"

    async def test_an_access_that_is_no_role_is_refused_before_anything_is_written(self, graph, stubs):
        with pytest.raises(HTTPException) as refused:
            await create(graph, access="no-such-role")
        assert refused.value.status_code == 422
        assert await new_entries(graph) == []


class TestThePersonsLabel:

    async def test_an_occupation_of_health_workers_labels_the_person(self, graph, stubs):
        await create(graph, effector_type=graph["hcw_type"])
        rows, _ = await adb.cypher_query("MATCH (e:Effector {uid: $uid}) RETURN labels(e)", {"uid": graph["effector"]})
        assert "HealthWorker" in rows[0][0]

    async def test_any_other_occupation_leaves_it_alone(self, graph, stubs):
        await create(graph)
        rows, _ = await adb.cypher_query("MATCH (e:Effector {uid: $uid}) RETURN labels(e)", {"uid": graph["effector"]})
        assert "HealthWorker" not in rows[0][0]


class TestCreatorAndOwner:

    async def user(self, graph, key="user"):
        from access.asyncneomodels import User

        return await User.nodes.get(uid=graph[key])

    async def test_without_a_signed_in_user_there_is_neither(self, graph, stubs):
        await create(graph)
        [(uid, *_)] = await new_entries(graph)
        kinds = {kind for kind, _ in await links(uid)}
        assert "CREATED_BY" not in kinds and "OWNED_BY" not in kinds

    async def test_the_user_is_creator_and_owner_by_default(self, graph, stubs):
        stubs.user = await self.user(graph)
        await create(graph)
        [(uid, *_)] = await new_entries(graph)
        assert {("CREATED_BY", graph["user"]), ("OWNED_BY", graph["user"])} <= await links(uid)

    async def test_not_owning_leaves_the_user_only_the_creator(self, graph, stubs):
        stubs.user = await self.user(graph)
        await create(graph, isOwner=False)
        [(uid, *_)] = await new_entries(graph)
        found = await links(uid)
        assert ("CREATED_BY", graph["user"]) in found
        assert "OWNED_BY" not in {kind for kind, _ in found}


class TestMemberships:

    async def test_an_organization_and_an_entry_are_both_joined(self, graph, stubs):
        await create(graph, memberships=[graph["org"], graph["other_entry"]])
        [(uid, *_)] = await new_entries(graph)
        assert {("MEMBER_OF", graph["org"]), ("MEMBER_OF", graph["other_entry"])} <= await links(uid)

    async def test_a_uid_that_names_neither_is_refused_before_anything_is_written(self, graph, stubs):
        bad = new_uid()
        with pytest.raises(HTTPException) as refused:
            await create(graph, memberships=[graph["org"], bad])
        assert refused.value.status_code == 422
        assert refused.value.detail == {"code": "unknown_membership", "uids": [bad]}
        assert await new_entries(graph) == []
        stubs.clear.assert_not_awaited()


class TestRefusalsBeforeWriting:

    async def test_unknown_manages_slugs_are_refused(self, graph, stubs):
        with pytest.raises(HTTPException) as refused:
            await create(graph, manages=["no-such-condition"])
        assert refused.value.status_code == 422
        assert refused.value.detail["code"] == "unknown_target"
        assert await new_entries(graph) == []

    async def test_unknown_coverage_places_are_refused(self, graph, stubs):
        bad = new_uid()
        with pytest.raises(HTTPException) as refused:
            await create(graph, coverage=[bad])
        assert refused.value.status_code == 422
        assert refused.value.detail == {"code": "unknown_place", "uids": [bad]}
        assert await new_entries(graph) == []

    async def test_a_type_the_directory_does_not_offer_is_refused_to_staff(self, graph, stubs):
        from directory.offered_types import offer

        stubs.role = "staff"
        await offer(DIRECTORY, graph["hcw_type"])
        with pytest.raises(HTTPException) as refused:
            await create(graph)
        assert refused.value.status_code == 409
        assert await new_entries(graph) == []

    async def test_redeem_email_is_for_administrators_and_superusers_and_refused_before_writing(self, graph, stubs):
        stubs.role = "staff"
        with pytest.raises(HTTPException) as refused:
            await create(graph, redeemEmail="someone@example.com")
        assert refused.value.status_code == 403
        assert await new_entries(graph) == []

    async def test_an_administrator_may_set_it(self, graph, stubs):
        await create(graph, redeemEmail="someone@example.com")
        rows, _ = await adb.cypher_query("MATCH (e:Entry) WHERE e.redeemEmail IS NOT NULL RETURN e.redeemEmail")
        assert rows == [["someone@example.com"]]


class TestWhatItFindsFirst:

    async def test_asking_twice_within_five_minutes_makes_one_entry(self, graph, stubs):
        first = await create(graph)
        second = await create(graph)
        assert first.uid == second.uid
        assert len(await new_entries(graph)) == 1

    async def test_an_inactive_entry_of_the_same_three_is_reactivated(self, graph, stubs):
        old = new_uid()
        await adb.cypher_query(
            """
            MATCH (p:Effector {uid: $effector}), (t:EffectorType {uid: $type}), (f:Facility {uid: $facility})
            CREATE (e:Entry {uid: $old, active: false, createdAt: 1, access: 'anonymous'})
            CREATE (e)-[:HAS_EFFECTOR]->(p), (e)-[:HAS_EFFECTOR_TYPE]->(t), (e)-[:HAS_FACILITY]->(f)
            """,
            {**graph, "old": old},
        )
        result = await create(graph)
        assert result.uid == old
        found = await new_entries(graph)
        assert [(uid, active) for uid, active, *_ in found] == [(old, True)]

    async def test_an_active_entry_of_the_same_three_is_a_conflict(self, graph, stubs):
        await adb.cypher_query(
            """
            MATCH (p:Effector {uid: $effector}), (t:EffectorType {uid: $type}), (f:Facility {uid: $facility})
            CREATE (e:Entry {uid: $old, active: true, createdAt: 1, access: 'anonymous'})
            CREATE (e)-[:HAS_EFFECTOR]->(p), (e)-[:HAS_EFFECTOR_TYPE]->(t), (e)-[:HAS_FACILITY]->(f)
            """,
            {**graph, "old": new_uid()},
        )
        with pytest.raises(HTTPException) as refused:
            await create(graph)
        assert refused.value.status_code == 452
        assert len(await new_entries(graph)) == 1
