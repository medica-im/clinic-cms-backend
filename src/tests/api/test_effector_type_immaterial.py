"""A type whose entries have no premises of their own: a help line, a listening service.

`immaterial` is set by the console on the type, orthogonal to `nature` (a CMP is a
service with premises, a help line is a service without). An entry of such a type
shows no address, map or facility link, and gives its people no rights over the
facility it sits on through its porteur. It has to reach the frontend with every
entry, in the list and on the entry's own page; a type from before the property reads
as material, never as a guess the other way.
"""
import pytest
from asgiref.sync import sync_to_async

from api.transformers import createEffectorTypeResources
from api.types.allentry import EffectorType as ListEffectorType
from api.types.fullentry import EffectorType as FullEffectorType


class FakeTypeNode:
    def __init__(self, **extra):
        self.uid = "type-uid-001"
        self.name_fr = "ligne d'écoute"
        self.label_fr = "ligne d'écoute"
        self.slug_fr = "ligne-ecoute"
        self.synonyms_fr = None
        self.definition_fr = None
        for key, value in extra.items():
            setattr(self, key, value)


def test_the_type_object_carries_it():
    assert createEffectorTypeResources(FakeTypeNode(immaterial=True)).immaterial is True


@pytest.mark.parametrize("node", [FakeTypeNode(immaterial=None), FakeTypeNode()], ids=["unset", "absent"])
def test_a_type_from_before_the_property_is_material(node):
    assert createEffectorTypeResources(node).immaterial is False


def test_the_entry_list_serves_it():
    type_dict = createEffectorTypeResources(FakeTypeNode(immaterial=True)).__dict__
    assert ListEffectorType(**type_dict).model_dump()["immaterial"] is True


def test_the_entry_page_serves_it():
    type_dict = createEffectorTypeResources(FakeTypeNode(immaterial=True)).__dict__
    type_dict["labels"] = []
    assert FullEffectorType(**type_dict).model_dump()["immaterial"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_console_sets_it_and_a_patch_changes_only_that(neo4j_graph):
    from api.serializers.effector_type import create_effector_type, get_effector_type, update_effector_type
    from api.types.effector_type import EffectorTypePatch, EffectorTypePost

    created = await create_effector_type(
        EffectorTypePost(name_fr="ligne", label_fr="ligne", slug_fr="ligne", nature="service", immaterial=True)
    )
    assert created.immaterial is True
    assert (await sync_to_async(get_effector_type)(uid=created.uid)).immaterial is True

    updated = await update_effector_type(created.uid, EffectorTypePatch(immaterial=False))
    assert updated.immaterial is False
    assert updated.nature == "service"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_type_created_without_it_is_material(neo4j_graph):
    from api.serializers.effector_type import create_effector_type
    from api.types.effector_type import EffectorTypePost

    created = await create_effector_type(EffectorTypePost(name_fr="cabinet", label_fr="cabinet", slug_fr="cabinet"))
    assert created.immaterial is False
