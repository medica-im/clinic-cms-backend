"""A type's synonyms: none is no property, never `[]`.

The console sends `synonyms_fr` and `synonyms_en` as `[]` when the file has none, on
every create and on a patch that removes the last one, and the API stored what it was
sent: 78 of dev's effector types and 83 of staging's held `[]`, where the rest held
nothing. The console and the readers already take null and `[]` as the same (`?? []`),
so one spelling costs nothing: no synonyms is no property, like the entry's payers.
"""
import pytest

from api.types.effector_type import EffectorTypePatch, EffectorTypePost

POST = dict(name_fr="ligne", label_fr="ligne", slug_fr="ligne")


@pytest.mark.parametrize("field", ["synonyms_fr", "synonyms_en"])
class TestTheInputs:
    def test_an_empty_list_on_create_is_none(self, field):
        assert getattr(EffectorTypePost(**POST, **{field: []}), field) is None

    def test_an_empty_list_on_patch_is_none(self, field):
        assert getattr(EffectorTypePatch(**{field: []}), field) is None

    def test_a_patch_that_sends_it_still_clears_it(self, field):
        """Sent, even empty, it is in model_fields_set: the serializer clears the stored one."""
        assert field in EffectorTypePatch(**{field: []}).model_fields_set

    def test_a_patch_that_leaves_it_out_leaves_it_alone(self, field):
        assert field not in EffectorTypePatch(name_fr="x").model_fields_set

    def test_synonyms_are_kept(self, field):
        assert getattr(EffectorTypePost(**POST, **{field: ["IDE"]}), field) == ["IDE"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_created_type_stores_no_property_for_no_synonyms(neo4j_graph):
    from api.serializers.effector_type import create_effector_type

    created = await create_effector_type(EffectorTypePost(**POST, synonyms_fr=[], synonyms_en=[]))
    rows, _ = await neo4j_graph.cypher_query(
        "MATCH (t:EffectorType {uid: $uid}) RETURN t.synonyms_fr, t.synonyms_en", {"uid": created.uid})
    assert rows[0] == [None, None]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_removing_the_last_synonym_leaves_no_property(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, update_effector_type

    created = await create_effector_type(EffectorTypePost(**POST, synonyms_fr=["IDE"]))
    await update_effector_type(created.uid, EffectorTypePatch(synonyms_fr=[]))
    rows, _ = await neo4j_graph.cypher_query(
        "MATCH (t:EffectorType {uid: $uid}) RETURN t.synonyms_fr", {"uid": created.uid})
    assert rows[0] == [None]
