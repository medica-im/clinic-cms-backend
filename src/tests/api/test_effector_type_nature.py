"""What an entry of this type does: a profession, a service or an activity.

An entry is an effector (a physical or legal person) doing something (its
effector type) somewhere (its facility). What it does decides how it is
written: a profession is practised by a person, so its label agrees with that
person's grammatical gender (infirmière, infirmier); a service is provided by a
structure, an activity is carried out — each has one form, whoever the
effector. The entry form therefore asks for a gender only for a profession.

`nature` says which. It is written by the console with the rest of the type,
and absent on types from before it: those read as None, not as a guess.
"""
import pytest
from asgiref.sync import sync_to_async
from pydantic import ValidationError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def post(**overrides):
    from api.types.effector_type import EffectorTypePost

    name = overrides.pop("name", "infirmier")
    return EffectorTypePost(name_fr=name, label_fr=name, slug_fr=name, **overrides)


@pytest.mark.parametrize("nature", ["profession", "service", "activity"])
async def test_a_type_says_what_its_entries_do(neo4j_graph, nature):
    from api.serializers.effector_type import create_effector_type, get_effector_type

    created = await create_effector_type(post(name=nature, nature=nature))

    assert created.nature == nature
    assert (await sync_to_async(get_effector_type)(uid=created.uid)).nature == nature


async def test_nothing_else_is_a_nature(neo4j_graph):
    with pytest.raises(ValidationError):
        post(nature="person")


async def test_a_patch_changes_only_that(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, update_effector_type
    from api.types.effector_type import EffectorTypePatch

    created = await create_effector_type(post(name="pharmacie", nature="profession"))

    updated = await update_effector_type(created.uid, EffectorTypePatch(nature="service"))

    assert updated.nature == "service"
    assert updated.name_fr == "pharmacie"


async def test_a_type_from_before_the_property_has_none(neo4j_graph):
    from api.serializers.effector_type import get_effector_type

    await neo4j_graph.cypher_query(
        "CREATE (:EffectorType {uid: 'old0000000000000000000000000000b', name_fr: 'kiné', label_fr: 'kiné', slug_fr: 'kine'})"
    )

    assert (await sync_to_async(get_effector_type)(uid="old0000000000000000000000000000b")).nature is None
