"""api/serializers/effector.py: finding, creating and updating the "who" of an entry.

An Effector is the person or body an entry lists. `get_effectors` is sync (`db`)
and filters through the entries that name an effector; the other lookups are
async and walk ownership (OWNED_BY / CREATED_BY, effector to user) and shared
access to entries. Writes go through neomodel's async models.

get_effectors has a branch for "no filter at all" that never runs: it tests the
builtin `filter`, which is always truthy. With nothing asked it therefore
answers through the entry join, so only effectors that have an entry come back.
That is what the first tests pin.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from api.serializers.effector import (
    create_effector,
    get_all_effectors,
    get_effector,
    get_effectors,
    get_effectors_by_entry_colleagues,
    get_effectors_by_user,
    update_effector,
)
from api.types.effector import EffectorPost

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def new_uid():
    return uuid.uuid4().hex


@pytest.fixture
async def graph(neo4j_graph):
    """Three people: one owned by the user, one created by them, one nobody's with no entry.

    The first two each have an entry at a facility in a commune of a department;
    the second pair of users share access to the first entry.
    """
    uids = {name: new_uid() for name in (
        "dept", "commune", "facility", "facility2", "type", "type2", "owned", "created", "orphan",
        "entry1", "entry2", "user", "colleague", "stranger", "access_u", "access_c", "access_s",
    )}
    await adb.cypher_query(
        """
        CREATE (d:DepartmentOfFrance {uid: $dept, code: '69', name: 'Rhône'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: $commune, name_fr: 'Lyon'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
        CREATE (f1:Facility {uid: $facility})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (f2:Facility {uid: $facility2})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (t1:EffectorType {uid: $type}), (t2:EffectorType {uid: $type2})
        CREATE (p1:Effector {uid: $owned, name_fr: 'Owned', creator_directory: 'dir-a'})
        CREATE (p2:Effector {uid: $created, name_fr: 'Created', creator_directory: 'dir-b'})
        CREATE (:Effector {uid: $orphan, name_fr: 'Orphan'})
        CREATE (e1:Entry {uid: $entry1})-[:HAS_FACILITY]->(f1)
        CREATE (e1)-[:HAS_EFFECTOR]->(p1), (e1)-[:HAS_EFFECTOR_TYPE]->(t1)
        CREATE (e2:Entry {uid: $entry2})-[:HAS_FACILITY]->(f2)
        CREATE (e2)-[:HAS_EFFECTOR]->(p2), (e2)-[:HAS_EFFECTOR_TYPE]->(t2)
        CREATE (u:User {uid: $user}), (co:User {uid: $colleague}), (s:User {uid: $stranger})
        CREATE (p1)-[:OWNED_BY]->(u), (p2)-[:CREATED_BY]->(u)
        CREATE (u)-[:HAS_ACCESS]->(:Access {uid: $access_u})-[:ACCESS_TO]->(e1)
        CREATE (co)-[:HAS_ACCESS]->(:Access {uid: $access_c})-[:ACCESS_TO]->(e1)
        CREATE (s)-[:HAS_ACCESS]->(:Access {uid: $access_s})-[:ACCESS_TO]->(e2)
        """,
        uids,
    )
    return uids


def names(effectors):
    return sorted(e.name_fr for e in effectors)


class TestGetEffectors:

    async def test_by_uid(self, graph):
        found = await sync_to_async(get_effectors)(uid=graph["owned"])
        assert names(found) == ["Owned"]

    async def test_by_a_uid_that_names_nothing(self, graph):
        assert await sync_to_async(get_effectors)(uid=new_uid()) == []

    async def test_by_owner(self, graph):
        found = await sync_to_async(get_effectors)(owner=graph["user"])
        assert names(found) == ["Owned"]

    async def test_by_an_owner_with_nothing(self, graph):
        assert await sync_to_async(get_effectors)(owner=graph["stranger"]) == []

    async def test_with_no_filter_only_effectors_that_have_an_entry_come_back(self, graph):
        found = await sync_to_async(get_effectors)()
        assert names(found) == ["Created", "Owned"]

    async def test_by_effector_type(self, graph):
        assert names(await sync_to_async(get_effectors)(effector_type=graph["type2"])) == ["Created"]

    async def test_by_facility(self, graph):
        assert names(await sync_to_async(get_effectors)(facility=graph["facility"])) == ["Owned"]

    async def test_by_commune_both_places_share(self, graph):
        assert names(await sync_to_async(get_effectors)(commune=graph["commune"])) == ["Created", "Owned"]

    async def test_by_department_code(self, graph):
        found = await sync_to_async(get_effectors)(department_of_france="69")
        assert names(found) == ["Created", "Owned"]
        assert await sync_to_async(get_effectors)(department_of_france="01") == []

    async def test_by_the_directory_that_created_it(self, graph):
        assert names(await sync_to_async(get_effectors)(directory="dir-b")) == ["Created"]

    async def test_filters_combine(self, graph):
        found = await sync_to_async(get_effectors)(effector_type=graph["type"], directory="dir-b")
        assert found == []

    async def test_a_facility_wins_over_a_commune(self, graph):
        found = await sync_to_async(get_effectors)(facility=graph["facility"], commune=new_uid())
        assert names(found) == ["Owned"]

    async def test_it_carries_the_effectors_fields(self, graph):
        [found] = await sync_to_async(get_effectors)(uid=graph["owned"])
        assert found.uid == graph["owned"]
        assert found.creator_directory == "dir-a"


class TestGetEffector:

    async def test_the_first_match(self, graph):
        found = await sync_to_async(get_effector)(uid=graph["created"])
        assert found.name_fr == "Created"

    async def test_nothing_found_raises(self, graph):
        with pytest.raises(Exception):
            await sync_to_async(get_effector)(uid=new_uid())


class TestLookupsThatWalkTheGraph:

    async def test_by_user_gives_what_they_own_or_created(self, graph):
        assert names(await get_effectors_by_user(graph["user"])) == ["Created", "Owned"]

    async def test_by_a_user_with_none(self, graph):
        assert await get_effectors_by_user(graph["stranger"]) == []

    async def test_by_user_lists_one_effector_once(self, graph):
        await adb.cypher_query(
            "MATCH (p:Effector {uid: $owned}), (u:User {uid: $user}) MERGE (p)-[:CREATED_BY]->(u)", graph
        )
        assert names(await get_effectors_by_user(graph["user"])).count("Owned") == 1

    async def test_all_effectors_includes_those_with_no_entry(self, graph):
        assert names(await get_all_effectors()) == ["Created", "Orphan", "Owned"]

    async def test_no_effectors_at_all_lists_none(self, neo4j_graph):
        assert await get_all_effectors() == []

    async def test_colleagues_effectors_are_those_of_people_sharing_an_entry(self, graph):
        await adb.cypher_query(
            "MATCH (p:Effector {uid: $orphan}), (u:User {uid: $colleague}) MERGE (p)-[:OWNED_BY]->(u)", graph
        )
        assert names(await get_effectors_by_entry_colleagues(graph["user"])) == ["Orphan"]

    async def test_a_person_with_no_shared_entry_has_no_colleagues(self, graph):
        assert await get_effectors_by_entry_colleagues(graph["stranger"]) == []

    async def test_the_colleague_sees_the_users_effectors_and_not_their_own(self, graph):
        await adb.cypher_query(
            "MATCH (u:User {uid: $colleague}) CREATE (:Effector {uid: 'mine', name_fr: 'Mine'})-[:OWNED_BY]->(u)",
            graph,
        )
        assert names(await get_effectors_by_entry_colleagues(graph["colleague"])) == ["Created", "Owned"]


class TestCreateEffector:

    def post(self, **over):
        return EffectorPost(**{"name_fr": "Dr Nouveau", "gender": "F", **over})

    @pytest.fixture
    def signed_in(self, graph):
        from access.asyncneomodels import User

        async def user(jwt):
            return await User.nodes.get(uid=graph["user"])

        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(side_effect=user)):
            yield

    @pytest.fixture
    async def directory(self, neo4j_graph):
        await adb.cypher_query("CREATE (:Directory {name: 'creating-dir'})")

    async def test_a_new_effector_is_saved_with_defaults(self, graph, directory):
        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            made = await create_effector(self.post(), "creating-dir", {})
        assert made.name_fr == "Dr Nouveau"
        assert made.label_fr == "Dr Nouveau"
        assert made.slug_fr == "dr-nouveau"
        assert made.gender == "F"
        assert made.creator_directory == "creating-dir"

    async def test_given_labels_are_kept(self, graph, directory):
        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            made = await create_effector(self.post(label_fr="Docteure", slug_fr="docteure"), "creating-dir", {})
        assert (made.label_fr, made.slug_fr) == ("Docteure", "docteure")

    async def test_the_signed_in_user_becomes_creator_and_owner(self, graph, directory, signed_in):
        made = await create_effector(self.post(), "creating-dir", {})
        rows, _ = await adb.cypher_query(
            "MATCH (:Effector {uid: $uid})-[r]->(u:User) RETURN type(r), u.uid", {"uid": made.uid}
        )
        assert {tuple(r) for r in rows} == {("CREATED_BY", graph["user"]), ("OWNED_BY", graph["user"])}

    async def test_without_a_user_there_are_no_links(self, graph, directory):
        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            made = await create_effector(self.post(), "creating-dir", {})
        rows, _ = await adb.cypher_query("MATCH (:Effector {uid: $uid})-[r]->() RETURN count(r)", {"uid": made.uid})
        assert rows[0][0] == 0

    @pytest.mark.parametrize("slug", [None, "dr-nouveau"])
    async def test_asking_twice_at_once_returns_the_same_effector(self, graph, directory, slug):
        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            first = await create_effector(self.post(slug_fr=slug), "creating-dir", {})
            second = await create_effector(self.post(slug_fr=slug), "creating-dir", {})
        assert first.uid == second.uid
        rows, _ = await adb.cypher_query("MATCH (e:Effector {name_fr: 'Dr Nouveau'}) RETURN count(e)")
        assert rows[0][0] == 1

    async def test_the_same_name_long_after_is_a_new_effector(self, graph, directory):
        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            first = await create_effector(self.post(), "creating-dir", {})
            await adb.cypher_query("MATCH (e:Effector {uid: $uid}) SET e.createdAt = 1", {"uid": first.uid})
            second = await create_effector(self.post(), "creating-dir", {})
        assert first.uid != second.uid

    async def test_an_unknown_directory_is_an_error(self, graph, directory):
        from directory.models.agraph import Directory

        with patch("api.serializers.effector.get_neo4j_user", AsyncMock(return_value=None)):
            with pytest.raises(Directory.DoesNotExist):
                await create_effector(self.post(name_fr="Ailleurs"), "no-such-directory", {})


class TestUpdateEffector:

    @pytest.fixture
    def cleared(self):
        with patch("api.serializers.effector.clear_cache", new_callable=AsyncMock) as mock:
            yield mock

    async def test_the_fields_sent_change_and_the_rest_stay(self, graph, cleared):
        updated = await update_effector(graph["owned"], {"label_fr": "Nouveau label"}, SimpleNamespace())
        assert updated.label_fr == "Nouveau label"
        assert updated.name_fr == "Owned"

    async def test_the_entries_cache_is_cleared(self, graph, cleared):
        await update_effector(graph["owned"], {"name_fr": "Renamed"}, SimpleNamespace())
        cleared.assert_awaited_once()
        assert cleared.await_args.args[0] == "v2:entries"

    async def test_a_health_worker_field_updates_a_health_worker(self, graph, cleared):
        await adb.cypher_query("MATCH (p:Effector {uid: $owned}) SET p:HealthWorker", graph)
        updated = await update_effector(graph["owned"], {"rpps": 12345678901}, SimpleNamespace())
        assert updated.rpps == 12345678901

    async def test_an_unknown_effector_is_an_error(self, graph, cleared):
        from directory.models.agraph import Effector

        with pytest.raises(Effector.DoesNotExist):
            await update_effector(new_uid(), {"name_fr": "x"}, SimpleNamespace())
        cleared.assert_not_awaited()
