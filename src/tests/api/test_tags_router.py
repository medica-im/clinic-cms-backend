"""Tag categories, tags, and tagging an entry.

Read through neomodel (`Tag.nodes`, `TagCategory.nodes`) and written with raw
Cypher. The empty cases are the ones that had no test: no categories, no tags,
an entry with nothing to add or remove, and an unknown tag.

`authorize_api` is patched; so is the cache clear, which is asserted on: it must
happen when a tag changed and only then.
"""
import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    from neomodel import adb

    uids = {name: uuid.uuid4().hex for name in ("category", "other_category", "tag", "other_tag", "entry")}
    await adb.cypher_query(
        """
        CREATE (c:TagCategory {uid: $category, name: 'langues', label: 'Langues', labelShort: 'L'})
        CREATE (o:TagCategory {uid: $other_category, name: 'accès', label: 'Accès'})
        CREATE (t:Tag {uid: $tag, name: 'anglais', label: 'Anglais', synonyms: ['english']})-[:IS_A]->(c)
        CREATE (u:Tag {uid: $other_tag, name: 'rampe', label: 'Rampe'})-[:IS_A]->(o)
        CREATE (:Entry {uid: $entry})
        """,
        uids,
    )
    return uids


@pytest.fixture
def signed_in(patch_jwt):
    jwt = {"providerAccountId": "tags-sub", "sub": "tags-sub", "email": "a@example.com", "name": "A"}
    with ExitStack() as stack:
        stack.enter_context(patch_jwt(jwt))
        stack.enter_context(patch("api.routers.tags.authorize_api", AsyncMock(return_value=True)))
        yield


@pytest.fixture
def cleared():
    with patch("api.serializers.tags.clear_cache", new_callable=AsyncMock) as mock:
        yield mock


async def tag_uids_of(entry_uid):
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        "MATCH (t:Tag)-[:TAGS]->(:Entry {uid: $uid}) RETURN t.uid", {"uid": entry_uid}
    )
    return {row[0] for row in rows}


class TestTagCategories:

    async def test_no_categories_lists_none(self, client, neo4j_graph):
        r = await client.get("/tag_categories")
        assert r.status_code == 200
        assert r.json() == []

    async def test_categories_list_with_their_fields(self, client, graph):
        r = await client.get("/tag_categories")
        assert r.status_code == 200
        by_name = {c["name"]: c for c in r.json()}
        assert set(by_name) == {"langues", "accès"}
        assert by_name["langues"]["uid"] == graph["category"]
        assert by_name["langues"]["label"] == "Langues"
        assert by_name["langues"]["labelShort"] == "L"
        assert by_name["accès"]["labelShort"] is None

    async def test_a_category_serves_its_effector_types(self, client, graph):
        from neomodel import adb

        await adb.cypher_query(
            "MATCH (c:TagCategory {uid: $category}) CREATE (:EffectorType {uid: 'et-1'})-[:HAS_TAG_CATEGORY]->(c)",
            graph,
        )
        r = await client.get(f"/tag_categories/{graph['category']}")
        assert r.status_code == 200
        assert r.json()["uid"] == graph["category"]
        assert r.json()["effector_types"] == ["et-1"]


    async def test_an_unknown_category_is_not_found(self, client, graph):
        r = await client.get(f"/tag_categories/{uuid.uuid4().hex}")
        assert r.status_code == 404


class TestTags:

    async def test_every_tag_carries_its_category(self, client, graph):
        r = await client.get("/tags")
        assert r.status_code == 200
        by_name = {t["name"]: t for t in r.json()}
        assert by_name["anglais"]["category"] == graph["category"]
        assert by_name["anglais"]["synonyms"] == ["english"]
        assert by_name["rampe"]["category"] == graph["other_category"]

    async def test_tags_filter_by_category_name(self, client, graph):
        r = await client.get("/tags", params={"category": "langues"})
        assert r.status_code == 200
        assert [t["uid"] for t in r.json()] == [graph["tag"]]
        assert r.json()[0]["category"] == graph["category"]

    async def test_a_category_without_tags_lists_none(self, client, graph):
        from neomodel import adb

        await adb.cypher_query("CREATE (:TagCategory {uid: 'empty', name: 'vide', label: 'Vide'})")
        r = await client.get("/tags", params={"category": "vide"})
        assert r.status_code == 200
        assert r.json() == []

    async def test_no_tags_at_all_lists_none(self, client, neo4j_graph):
        r = await client.get("/tags")
        assert r.status_code == 200
        assert r.json() == []


class TestTaggingAnEntry:

    def body(self, graph, add=None, remove=None, entry=None):
        return {"entry": entry or graph["entry"], "addTags": add, "removeTags": remove}

    async def test_adding_a_tag(self, client, graph, signed_in, cleared):
        r = await client.post("/entry/tag", json=self.body(graph, add=[graph["tag"]]))
        assert r.status_code == 200
        assert await tag_uids_of(graph["entry"]) == {graph["tag"]}
        cleared.assert_awaited_once()

    async def test_adding_it_twice_tags_it_once(self, client, graph, signed_in, cleared):
        for _ in range(2):
            await client.post("/entry/tag", json=self.body(graph, add=[graph["tag"]]))
        from neomodel import adb
        rows, _ = await adb.cypher_query(
            "MATCH (:Tag {uid: $tag})-[r:TAGS]->(:Entry {uid: $entry}) RETURN count(r)", graph
        )
        assert rows[0][0] == 1

    async def test_removing_a_tag(self, client, graph, signed_in, cleared):
        await client.post("/entry/tag", json=self.body(graph, add=[graph["tag"], graph["other_tag"]]))
        r = await client.post("/entry/tag", json=self.body(graph, remove=[graph["tag"]]))
        assert r.status_code == 200
        assert await tag_uids_of(graph["entry"]) == {graph["other_tag"]}

    async def test_removing_one_that_is_not_there_changes_nothing(self, client, graph, signed_in, cleared):
        r = await client.post("/entry/tag", json=self.body(graph, remove=[graph["tag"]]))
        assert r.status_code == 200
        assert await tag_uids_of(graph["entry"]) == set()

    async def test_nothing_to_add_or_remove_leaves_the_cache_alone(self, client, graph, signed_in, cleared):
        r = await client.post("/entry/tag", json=self.body(graph))
        assert r.status_code == 200
        cleared.assert_not_awaited()

    async def test_an_unknown_tag_is_not_found(self, client, graph, signed_in, cleared):
        r = await client.post("/entry/tag", json=self.body(graph, add=[uuid.uuid4().hex]))
        assert r.status_code == 404
        cleared.assert_not_awaited()

    async def test_an_unknown_entry_is_not_found(self, client, graph, signed_in, cleared):
        r = await client.post("/entry/tag", json=self.body(graph, add=[graph["tag"]], entry=uuid.uuid4().hex))
        assert r.status_code == 404

    async def test_tagging_without_signing_in_is_refused(self, client, graph):
        r = await client.post("/entry/tag", json=self.body(graph, add=[graph["tag"]]))
        assert r.status_code == 401
