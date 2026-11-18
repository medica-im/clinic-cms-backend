"""The word for the kind of place a profession is practised in.

A facility with no name of its own is named in its address by what is done
there: "cabinet médical", "cabinet de kinésithérapie". The console writes the
word on the type, and a type below another inherits the nearest ancestor's
(slug_base), so "médecin" carries it once for every kind of doctor.
"""
import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def post(**overrides):
    from api.types.effector_type import EffectorTypePost

    name = overrides.pop("name", "kinésithérapeute")
    return EffectorTypePost(name_fr=name, label_fr=name, slug_fr=name, **overrides)


async def test_a_type_carries_the_word_for_its_place(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, get_effector_type

    created = await create_effector_type(post(facility_noun_fr="cabinet de kinésithérapie"))

    assert created.facility_noun_fr == "cabinet de kinésithérapie"
    assert (await sync_to_async(get_effector_type)(uid=created.uid)).facility_noun_fr == "cabinet de kinésithérapie"


async def test_a_patch_can_set_it_later(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, update_effector_type
    from api.types.effector_type import EffectorTypePatch

    created = await create_effector_type(post(name="dentiste"))

    updated = await update_effector_type(created.uid, EffectorTypePatch(facility_noun_fr="cabinet dentaire"))

    assert updated.facility_noun_fr == "cabinet dentaire"
    assert updated.name_fr == "dentiste"


async def test_a_type_without_one_has_none(neo4j_graph):
    from api.serializers.effector_type import create_effector_type

    assert (await create_effector_type(post(name="orthoptiste"))).facility_noun_fr is None
