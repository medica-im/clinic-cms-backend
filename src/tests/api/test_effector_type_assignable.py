"""Whether entries may have an effector type, or it only groups others.

Nurse and IPA are both professions an entry may have, though IPA IS_A nurse;
"paramédical" only gathers professions. The tree cannot tell them apart, so
each node says it: `assignable`, true by default — every node written before
the property existed is a type entries may have, as it always was.
"""
import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def post(**overrides):
    from api.types.effector_type import EffectorTypePost

    name = overrides.pop("name", "paramédical")
    return EffectorTypePost(name_fr=name, label_fr=name, slug_fr=name.replace("é", "e"), **overrides)


async def test_a_type_is_assignable_unless_told_otherwise(neo4j_graph):
    from api.serializers.effector_type import create_effector_type

    assert (await create_effector_type(post(name="infirmier"))).assignable is True


async def test_a_category_says_so(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, get_effector_type

    created = await create_effector_type(post(assignable=False))

    assert created.assignable is False
    assert (await sync_to_async(get_effector_type)(created.uid)).assignable is False


async def test_a_patch_changes_only_that(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, update_effector_type
    from api.types.effector_type import EffectorTypePatch

    created = await create_effector_type(post())

    updated = await update_effector_type(created.uid, EffectorTypePatch(assignable=False))

    assert updated.assignable is False
    assert updated.name_fr == "paramédical"


async def test_a_node_from_before_the_property_is_assignable(neo4j_graph):
    from api.serializers.effector_type import get_effector_type

    await neo4j_graph.cypher_query(
        "CREATE (:EffectorType {uid: 'old0000000000000000000000000000a', name_fr: 'kiné', label_fr: 'kiné', slug_fr: 'kine'})"
    )

    assert (await sync_to_async(get_effector_type)("old0000000000000000000000000000a")).assignable is True
