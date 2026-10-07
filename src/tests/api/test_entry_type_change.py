"""Changing an entry's effector type, against a real Neo4j.

The write replaces a single-valued edge nothing in the database guards, so it
runs in one transaction that checks the entry's shape before and after
(directory.entry_shape) and commits nothing when either check fails. This
file drives change_entry_type on a throwaway graph (the scratch database of
conftest_neo4j) and reads the result back:

* the entry has exactly one HAS_EFFECTOR_TYPE, the new one;
* tags whose category is not linked to the new type are gone, the others
  (and tags with no category) stay;
* the new slug is set; the person gets HealthWorker for an HCW type;
* an entry already malformed is refused and left as it was;
* a result found malformed after the write is rolled back.

Slug generation and the EntrySlug row are stubbed: they have their own tests
(test_entry_slug_history.py), and both reach Postgres from a worker thread,
where an async test's database is not visible.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from neomodel import adb

from api.serializers.entry_type import EntryTypeRefused, change_entry_type
from directory.entry_type_edit import TypeEditPermission

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRY, PERSON, PLACE = "e" * 32, "p" * 32, "f" * 32
OLD_TYPE, NEW_TYPE = "a" * 32, "b" * 32


@pytest.fixture
async def entry(neo4j_graph):
    """An IDE entry at one place, in a directory, with three tags: one whose
    category is linked only to the old type, one whose category is linked to
    both, one with no category."""
    await adb.cypher_query(
        """
        CREATE (d:Directory {name: 'test'})
        CREATE (e:Entry {uid: $entry, slug: 'dupont-jean-ide-69', active: true})
        CREATE (p:Effector {uid: $person, name_fr: 'Jean Dupont'})
        CREATE (f:Facility {uid: $place, zip: '69001'})
        CREATE (old:EffectorType {uid: $old, name_fr: 'infirmier'})
        CREATE (new:EffectorType:HCW {uid: $new, name_fr: 'infirmier en pratique avancée'})
        CREATE (d)-[:HAS_ENTRY]->(e)
        CREATE (e)-[:HAS_EFFECTOR]->(p), (e)-[:HAS_FACILITY]->(f), (e)-[:HAS_EFFECTOR_TYPE]->(old)
        CREATE (only_old:TagCategory {label: 'only old'})<-[:HAS_TAG_CATEGORY]-(old)
        CREATE (both:TagCategory {label: 'both'})<-[:HAS_TAG_CATEGORY]-(old)
        CREATE (new)-[:HAS_TAG_CATEGORY]->(both)
        CREATE (:Tag {uid: 'unfit', label: 'Unfit'})-[:IS_A]->(only_old)
        CREATE (:Tag {uid: 'fit', label: 'Fit'})-[:IS_A]->(both)
        CREATE (:Tag {uid: 'free', label: 'Free'})
        WITH e
        MATCH (t:Tag) CREATE (t)-[:TAGS]->(e)
        """,
        {"entry": ENTRY, "person": PERSON, "place": PLACE, "old": OLD_TYPE, "new": NEW_TYPE},
    )
    with (
        patch("api.serializers.entry_type.generate_entry_slugs", AsyncMock(return_value=["dupont-jean-ipa-69"])),
        patch("api.serializers.entry_type.EntrySlug", MagicMock()),
    ):
        yield


def context():
    return SimpleNamespace(
        uid=ENTRY,
        slug="dupont-jean-ide-69",
        type_uid=OLD_TYPE,
        effector_uid=PERSON,
        facility_uid=PLACE,
        created_at_ms=None,
        caller_uid="u1",
        permission=TypeEditPermission(True, None, None, None),
        role="administrator",
        directory="test",  # offers no set: every type passes
    )


async def read(query, **params):
    rows, _ = await adb.cypher_query(query, {"entry": ENTRY, **params})
    return rows


async def types():
    return [r[0] for r in await read("MATCH (:Entry {uid: $entry})-[:HAS_EFFECTOR_TYPE]->(t) RETURN t.uid")]


async def tags():
    return sorted(r[0] for r in await read("MATCH (t:Tag)-[:TAGS]->(:Entry {uid: $entry}) RETURN t.uid"))


async def test_the_type_is_replaced_and_only_it(entry):
    result = await change_entry_type(context(), NEW_TYPE)

    assert await types() == [NEW_TYPE]
    assert result["slug"] == "dupont-jean-ipa-69"
    assert (await read("MATCH (e:Entry {uid: $entry}) RETURN e.slug"))[0][0] == "dupont-jean-ipa-69"


async def test_tags_that_do_not_fit_the_new_type_are_removed(entry):
    result = await change_entry_type(context(), NEW_TYPE)

    assert await tags() == ["fit", "free"]
    assert result["removed_tags"] == [{"uid": "unfit", "label": "Unfit"}]


async def test_the_person_is_labelled_health_worker_for_an_hcw_type(entry):
    await change_entry_type(context(), NEW_TYPE)

    labels = (await read("MATCH (p:Effector {uid: $person}) RETURN labels(p)", person=PERSON))[0][0]
    assert "HealthWorker" in labels


async def test_an_entry_already_malformed_is_refused_and_left_alone(entry):
    await adb.cypher_query(
        "MATCH (e:Entry {uid: $entry}), (t:EffectorType {uid: $new}) CREATE (e)-[:HAS_EFFECTOR_TYPE]->(t)",
        {"entry": ENTRY, "new": NEW_TYPE},
    )

    with pytest.raises(EntryTypeRefused) as refused:
        await change_entry_type(context(), NEW_TYPE)

    assert refused.value.code == "malformed"
    assert refused.value.detail["problems"] == ["HAS_EFFECTOR_TYPE:2"]
    assert sorted(await types()) == sorted([OLD_TYPE, NEW_TYPE])
    assert await tags() == ["fit", "free", "unfit"]


async def test_a_result_found_malformed_is_rolled_back(entry):
    # The second shape check fails: nothing done inside the transaction stays.
    checks = iter([[], ["HAS_EFFECTOR_TYPE:2"]])
    with patch("api.serializers.entry_type.entry_shape_problems", AsyncMock(side_effect=lambda uid: next(checks))):
        with pytest.raises(EntryTypeRefused) as refused:
            await change_entry_type(context(), NEW_TYPE)

    assert refused.value.code == "malformed"
    assert await types() == [OLD_TYPE]
    assert await tags() == ["fit", "free", "unfit"]
    assert (await read("MATCH (e:Entry {uid: $entry}) RETURN e.slug"))[0][0] == "dupont-jean-ide-69"
