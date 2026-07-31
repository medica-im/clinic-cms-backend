"""Effector types keep their authored short label alongside the gendered one.

The graph node carries both a full name ("communauté professionnelle
territoriale de santé") and a short authored label ("CPTS", "IPA").
flex_effector_type_label replaces `label` with the gendered term from the Label
table so callers get "infirmière" / "infirmier"; types with no such term fall
back to the long name, which loses the short form.

`raw_label` keeps the graph label untouched so the UI can show the short
invariable form where space is tight (the Team Svelte component).
"""
import pytest
from unittest.mock import AsyncMock, patch

from api.transformers import createEffectorTypeResources


pytestmark = pytest.mark.asyncio


class FakeTypeNode:
    """Minimal stand-in for the EffectorType graph node."""

    def __init__(self, uid, name_fr, label_fr):
        self.uid = uid
        self.name_fr = name_fr
        self.label_fr = label_fr
        self.slug_fr = "cpts"
        self.synonyms_fr = None
        self.definition_fr = None


class FakeEffector:
    gender = "N"


def cpts_node():
    return FakeTypeNode(
        uid="type-uid-001",
        name_fr="communauté professionnelle territoriale de santé",
        label_fr="CPTS",
    )


def mock_label(value):
    """Patch the Label lookup as imported into the allentries serializer."""
    return patch(
        "api.serializers.allentries.Label.async_get_label",
        new_callable=AsyncMock,
        return_value=value,
    )


async def test_raw_label_holds_the_graph_label():
    type_object = createEffectorTypeResources(cpts_node())
    assert type_object.raw_label == "CPTS"


async def test_raw_label_survives_the_gendered_replacement():
    """No "label" term is recorded for CPTS, so `label` falls back to the long
    name — but the short form must still be reachable."""
    from api.serializers.allentries import flex_effector_type_label

    type_object = createEffectorTypeResources(cpts_node())
    with mock_label(None):
        result = await flex_effector_type_label(FakeEffector(), type_object)

    assert result.label == "communauté professionnelle territoriale de santé"
    assert result.raw_label == "CPTS"


async def test_gendered_term_still_wins_for_label():
    """raw_label is additive: a recorded term still populates `label`."""
    from api.serializers.allentries import flex_effector_type_label

    node = FakeTypeNode(uid="type-uid-002", name_fr="infirmière", label_fr="infirmière")
    type_object = createEffectorTypeResources(node)
    with mock_label("infirmières"):
        result = await flex_effector_type_label(FakeEffector(), type_object)

    assert result.label == "infirmières"
    assert result.raw_label == "infirmière"
