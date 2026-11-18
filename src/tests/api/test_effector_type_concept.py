"""Any effector type with a MeSH id keeps its concept's names.

`unique_ID` is declared on every type but `concept_fr` / `concept_en` were
declared on HCW only, so a plain type (an organisation, a category) dropped
them on save while the API answered success: the console applied EHPAD's
concept again and again.
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def post(**overrides):
    from api.types.effector_type import EffectorTypePost

    return EffectorTypePost(name_fr="EHPAD", label_fr="EHPAD", slug_fr="ehpad", unique_ID="D006707", **overrides)


async def stored(uid: str) -> tuple:
    from neomodel import adb

    rows, _ = await adb.cypher_query("MATCH (t:EffectorType {uid: $uid}) RETURN t.concept_fr, t.concept_en", {"uid": uid})
    return tuple(rows[0])


async def test_a_plain_type_keeps_its_concept_when_created(neo4j_graph):
    from api.serializers.effector_type import create_effector_type

    created = await create_effector_type(post(concept_fr="Maisons de retraite médicalisées", concept_en="Homes for the Aged"))

    assert await stored(created.uid) == ("Maisons de retraite médicalisées", "Homes for the Aged")


async def test_a_plain_type_keeps_its_concept_when_patched(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, update_effector_type
    from api.types.effector_type import EffectorTypePatch

    created = await create_effector_type(post())

    await update_effector_type(created.uid, EffectorTypePatch(concept_fr="Maisons de retraite médicalisées", concept_en="Homes for the Aged"))

    assert await stored(created.uid) == ("Maisons de retraite médicalisées", "Homes for the Aged")
