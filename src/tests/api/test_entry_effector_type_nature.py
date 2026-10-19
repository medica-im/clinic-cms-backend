"""An entry's effector type carries its nature, so the frontend can inflect it.

The directory heads each group of entries with the type's label, in the
singular or plural, feminine or masculine. Only a profession's label agrees
with its practitioners' gender; a service ("pharmacie") agrees in number only,
and an activity ("portage de repas à domicile") is invariable. The frontend
picks the form from `effector_type.nature`, which has to reach it with every
entry, in the list and on the entry's own page.
"""
import pytest

from api.transformers import createEffectorTypeResources
from api.types.allentry import EffectorType as ListEffectorType
from api.types.fullentry import EffectorType as FullEffectorType


class FakeTypeNode:
    """Minimal stand-in for the EffectorType graph node."""

    def __init__(self, **extra):
        self.uid = "type-uid-001"
        self.name_fr = "pharmacie"
        self.label_fr = "pharmacie"
        self.slug_fr = "pharmacie"
        self.synonyms_fr = None
        self.definition_fr = None
        for key, value in extra.items():
            setattr(self, key, value)


@pytest.mark.parametrize("nature", ["profession", "service", "activity"])
def test_the_type_object_carries_the_nature(nature):
    assert createEffectorTypeResources(FakeTypeNode(nature=nature)).nature == nature


@pytest.mark.parametrize("node", [FakeTypeNode(nature=None), FakeTypeNode()], ids=["unset", "absent"])
def test_a_type_without_a_nature_yet_has_none(node):
    assert createEffectorTypeResources(node).nature is None


def test_the_entry_list_serves_the_nature():
    type_dict = createEffectorTypeResources(FakeTypeNode(nature="service")).__dict__
    assert ListEffectorType(**type_dict).model_dump()["nature"] == "service"


def test_the_entry_page_serves_the_nature():
    type_dict = createEffectorTypeResources(FakeTypeNode(nature="activity")).__dict__
    type_dict["labels"] = []
    assert FullEffectorType(**type_dict).model_dump()["nature"] == "activity"
