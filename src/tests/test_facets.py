"""Who an entry is for, and how to reach it: the facets a GP filters on.

They belong to the entry, not its type: a CMP for adults and a CMP for older
people share type and porteur. Every facet is optional and null means unknown,
never "no": the selectors over-include, so a gap in the data drops nobody.

What is pinned here is the vocabulary (a typo is refused, not stored), the age
range (whole years, inclusive, a missing bound is open, never reversed) and the
matching rule the age selector uses.
"""
import pytest

from directory.facets import (
    ACCESS_MODES,
    AUDIENCES,
    CARE_LEVELS,
    WHO_CAN_CONTACT,
    check_age_range,
    check_choice,
    check_choices,
    matches_age,
)


@pytest.mark.parametrize("age_min, age_max", [(16, None), (None, 25), (12, 25), (0, 120), (18, 18), (None, None)])
def test_an_age_range_may_leave_either_bound_open(age_min, age_max):
    assert check_age_range(age_min, age_max) == (age_min, age_max)


@pytest.mark.parametrize("age_min, age_max", [(-1, None), (None, 121), (26, 25), (1.5, None), (True, None)])
def test_an_impossible_or_reversed_range_is_refused(age_min, age_max):
    with pytest.raises(ValueError):
        check_age_range(age_min, age_max)


@pytest.mark.parametrize(
    "age, expected",
    [(15, False), (16, True), (70, True), (None, True)],
)
def test_a_16_and_up_service_matches_from_16_and_an_unknown_age_matches_all(age, expected):
    assert matches_age(16, None, age) is expected


def test_the_bounds_are_inclusive():
    assert matches_age(12, 25, 12) and matches_age(12, 25, 25)
    assert not matches_age(12, 25, 11) and not matches_age(12, 25, 26)


def test_an_entry_that_states_no_age_matches_every_patient():
    assert matches_age(None, None, 3) and matches_age(None, None, 99)


def test_an_open_upper_bound_never_drops_a_seventy_year_old():
    assert matches_age(18, None, 70)


def test_a_choice_is_one_word_of_its_vocabulary():
    assert check_choice("referral", WHO_CAN_CONTACT, "who_can_contact") == "referral"
    assert check_choice(None, WHO_CAN_CONTACT, "who_can_contact") is None
    with pytest.raises(ValueError, match="who_can_contact"):
        check_choice("sur adressage", WHO_CAN_CONTACT, "who_can_contact")


def test_choices_come_back_without_repeats_in_the_order_of_the_vocabulary():
    assert check_choices(["online", "phone", "online"], ACCESS_MODES, "access_modes") == ["phone", "online"]
    assert check_choices([], CARE_LEVELS, "care_levels") == []
    assert check_choices(None, AUDIENCES, "audiences") is None


def test_one_unknown_word_refuses_the_whole_list():
    with pytest.raises(ValueError, match="care_levels"):
        check_choices(["urgence", "quaternary"], CARE_LEVELS, "care_levels")


def test_the_vocabularies_are_the_ones_of_the_plan():
    assert CARE_LEVELS == ("emergency", "primary", "secondary", "tertiary", "prevention")
    assert WHO_CAN_CONTACT == ("anyone", "referral", "professionals")
    assert ACCESS_MODES == ("phone", "walk_in", "appointment", "admission", "online", "teleexpertise", "home_visit")
    assert AUDIENCES == ("students", "caregivers", "parents", "women", "men", "lgbtqia", "older_adults")


def test_a_node_gives_its_facets_with_null_for_what_it_never_stored():
    from types import SimpleNamespace

    from directory.facets import ENTRY_FACETS, facets_of

    node = SimpleNamespace(age_min=16, who_can_contact="referral", care_levels=["primary"])
    found = facets_of(node)
    assert set(found) == set(ENTRY_FACETS)
    assert found["age_min"] == 16
    assert found["who_can_contact"] == "referral"
    assert found["care_levels"] == ["primary"]
    assert found["age_max"] is None
    assert found["free"] is None
