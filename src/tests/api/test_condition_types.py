"""What a Condition may say, before it reaches the graph.

A Condition is a node of the mental health tree: a DSM-5-TR chapter (kind
"chapter", no parent) or a disorder under one (kind "condition"). Nodes are
matched by slug, never by uid: the same node has a different uid on each Neo4j
server. ICD-11 codes are kept as the list the classification gives, so a
malformed code is refused here rather than seeded.
"""
import pytest
from pydantic import ValidationError

from api.types.condition import ConditionPatch, ConditionPost, node_properties

pytestmark = pytest.mark.no_db


def condition(**overrides):
    payload = {"slug": "addiction-alcool", "name_fr": "Alcool"}
    payload.update(overrides)
    return ConditionPost(**payload)


def test_a_condition_needs_only_a_slug_and_a_french_name():
    c = condition()
    assert c.kind == "condition"
    assert c.icd_11 == []
    assert c.synonyms_fr == []
    assert c.parent is None
    assert c.chapter is None


@pytest.mark.parametrize("slug", ["Alcool", "alcool_x", "-alcool", "alcool-", "al cool", ""])
def test_a_slug_is_lowercase_words_joined_by_hyphens(slug):
    with pytest.raises(ValidationError):
        condition(slug=slug)


@pytest.mark.parametrize("code", ["6C40", "6D11.5", "6A7", "07", "MG30", "6D7-6E0"])
def test_an_icd11_code_is_accepted(code):
    assert condition(icd_11=[code]).icd_11 == [code]


@pytest.mark.parametrize("code", ["6c40", "F32", "6", "6C40 ", "depression", "6C40.", "6C 40"])
def test_a_malformed_icd11_code_is_refused(code):
    with pytest.raises(ValidationError):
        condition(icd_11=[code])


def test_synonyms_are_trimmed_and_each_listed_once():
    c = condition(synonyms_fr=[" alcoolisme ", "alcoolisme", "Alcoolisme", "alcoolodépendance"])
    assert c.synonyms_fr == ["alcoolisme", "alcoolodépendance"]


def test_an_empty_synonym_is_dropped():
    assert condition(synonyms_fr=["", "  ", "alcoolisme"]).synonyms_fr == ["alcoolisme"]


def test_a_condition_cannot_be_its_own_parent():
    with pytest.raises(ValidationError):
        condition(parent="addiction-alcool")


def test_a_chapter_has_no_parent():
    with pytest.raises(ValidationError):
        condition(slug="troubles-depressifs", kind="chapter", parent="addictions")


def test_a_chapter_carries_its_number():
    assert condition(slug="troubles-depressifs", kind="chapter", chapter=4).chapter == 4


def test_a_chapter_number_is_a_dsm_chapter_not_gender_dysphoria_or_a_catch_all():
    for number in (0, 14, 20, 21, 22, 23):
        with pytest.raises(ValidationError):
            condition(chapter=number)


def test_a_patch_may_change_one_field_and_says_which_it_sent():
    patch = ConditionPatch(name_fr="Alcool (usage)")
    assert patch.model_fields_set == {"name_fr"}


def test_a_patch_may_clear_the_parent_explicitly():
    patch = ConditionPatch(parent=None)
    assert "parent" in patch.model_fields_set
    assert patch.parent is None


def test_a_patch_refuses_the_same_malformed_codes():
    with pytest.raises(ValidationError):
        ConditionPatch(icd_11=["F32"])


@pytest.mark.parametrize("field", ["name_fr", "kind", "icd_11", "synonyms_fr", "synonyms_en"])
def test_a_patch_cannot_null_a_field_every_condition_has(field):
    with pytest.raises(ValidationError):
        ConditionPatch(**{field: None})


@pytest.mark.parametrize("field", ["name_en", "label_fr", "chapter", "parent"])
def test_a_patch_may_null_an_optional_field(field):
    assert getattr(ConditionPatch(**{field: None}), field) is None


def test_a_patch_cannot_rename_the_slug():
    with pytest.raises(ValidationError):
        ConditionPatch(slug="autre")


def test_the_stored_properties_leave_the_parent_to_the_relationship():
    props = node_properties(condition(parent="troubles-lies-a-une-substance-et-troubles-addictifs", icd_11=["6C40"]))
    assert "parent" not in props
    assert props["icd_11"] == ["6C40"]
    assert props["slug"] == "addiction-alcool"
