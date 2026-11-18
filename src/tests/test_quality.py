"""Quality controls of the directory: what an entry must say, by what it is and what it offers.

A ligne d'écoute without a phone number is a line nobody can call; it went unnoticed because the
import had dropped the number and nothing looked for it. Every rule here is a warning, never a
refusal to save, and each has its own test: the rule fires for the entry that breaks it and for
no other, so a rule cannot grow to flag healthy entries.

`problems()` is a pure function of `EntryFacts`, so these tests need no database; the gathering of
the facts, and who may read the answer, are in tests/api/test_quality_api.py.
"""
import dataclasses

import pytest

from directory.quality import RULES, EntryFacts, problems


def healthy(**changes) -> EntryFacts:
    """A listed, placed, complete consultation: no problem."""
    base = EntryFacts(
        uid="e1",
        slug="cmp-lyon",
        name="CMP Lyon",
        label="CMP Lyon",
        type_slug="consultation-specialisee",
        immaterial=False,
        nature="service",
        listed=True,
        active=True,
        description="Consultations de psychiatrie, sur rendez-vous.",
        offers=["consultation"],
        who_can_contact="referral",
        care_levels=["secondary"],
        siren=None,
        has_porteur=False,
        coverage=0,
        schedules=[],
        has_location=True,
        phones=["0472000000"],
        emails=[],
        websites=[],
    )
    return dataclasses.replace(base, **changes)


def codes(**changes) -> list[str]:
    return [code for code, _ in problems(healthy(**changes))]


def test_a_complete_entry_has_no_problem():
    assert problems(healthy()) == []


def test_every_rule_has_a_code_and_a_severity_the_page_can_word():
    assert len({rule.code for rule in RULES}) == len(RULES)
    assert {rule.severity for rule in RULES} <= {"missing", "incomplete"}


def test_an_entry_that_is_not_listed_or_not_active_is_not_judged():
    bare = dict(description=None, offers=None, who_can_contact=None, phones=[], has_location=False)
    assert codes(listed=False, **bare) == []
    assert codes(active=False, **bare) == []


# --- every listed entry --------------------------------------------------------------


def test_no_phone_no_email_no_website_is_a_missing_contact():
    assert codes(phones=[]) == ["no_contact"]
    assert codes(phones=[], emails=["a@b.fr"]) == []
    assert codes(phones=[], websites=["https://x.fr"]) == []


def test_no_description_no_offers_no_access_are_incomplete():
    assert codes(description=None) == ["no_description"]
    assert codes(description="  ") == ["no_description"]
    assert codes(offers=None) == ["no_offers"]
    assert codes(offers=[]) == ["no_offers"]
    assert codes(who_can_contact=None) == ["no_access"]


def test_a_phone_is_ten_digits_from_zero_or_a_short_number():
    assert codes(phones=["0472000000"]) == []
    assert codes(phones=["3114"]) == []
    assert codes(phones=["119"]) == []
    assert codes(phones=["04 72 00 00 00"]) == ["phone_format"]
    assert codes(phones=["047200000"]) == ["phone_format"]
    assert codes(phones=["+33472000000"]) == ["phone_format"]


def test_an_acronym_with_no_full_name_has_nothing_to_show_below_its_title():
    assert codes(name="UNAFAM", label="UNAFAM") == ["acronym_without_full_name"]
    assert codes(name="UNAFAM", label="UNAFAM", nature="profession") == []
    assert codes(name="Union nationale de familles", label="UNAFAM") == []
    assert codes(name="Apsytude", label="Apsytude") == []
    assert codes(name="3919", label="3919") == []


def test_hours_written_in_the_description_belong_in_the_schedule():
    assert codes(description="Ouvert de 9 h à 21 h, 7 jours sur 7.") == ["hours_in_description"]
    assert codes(description="Permanence le mercredi, 13h30-16h30.") == ["hours_in_description"]
    assert codes(description="Ouvert de 9 h à 21 h.", schedules=["phone"]) == []
    assert codes(description="Écoute 24 h/24 et 7 j/7.", schedules=[]) == []


# --- placed and immaterial entries ---------------------------------------------------


def test_a_placed_entry_with_no_pin_has_no_address_to_show():
    assert codes(has_location=False) == ["no_location"]


def test_an_immaterial_entry_needs_a_coverage_and_a_porteur_not_a_place():
    line = dict(type_slug="ligne-ecoute", immaterial=True, offers=["listening"], who_can_contact="anyone",
                has_location=False, coverage=1, has_porteur=True, phones=["3114"])
    assert codes(**line) == []
    assert codes(**{**line, "coverage": 0}) == ["no_coverage"]
    assert codes(**{**line, "has_porteur": False}) == ["no_porteur"]


# --- by type -------------------------------------------------------------------------


LINE = dict(type_slug="ligne-ecoute", immaterial=True, offers=["listening"], who_can_contact="anyone",
            has_location=False, coverage=1, has_porteur=True, phones=["3114"])


def test_a_ligne_d_ecoute_without_a_phone_is_a_line_nobody_can_call():
    assert codes(**{**LINE, "phones": [], "websites": ["https://x.fr"]}) == ["line_without_phone"]
    assert codes(**{**LINE, "phones": [], "emails": ["a@b.fr"]}) == ["line_without_phone"]
    assert codes(**LINE) == []


def test_a_ligne_d_ecoute_says_it_is_reached_by_phone_when_it_says_how():
    assert codes(**{**LINE, "access_modes": ["online"]}) == ["line_access_not_phone"]
    assert codes(**{**LINE, "access_modes": ["phone", "online"]}) == []
    assert codes(**{**LINE, "access_modes": None}) == []


def test_an_on_site_permanence_needs_on_site_hours():
    permanence = dict(type_slug="permanence-accueil-ecoute")
    assert codes(**permanence) == ["no_on_site_hours"]
    assert codes(**permanence, schedules=["on_site"]) == []
    assert codes(**permanence, schedules=["phone"]) == ["no_on_site_hours"]


def test_an_emergency_department_is_an_emergency_level_of_care():
    assert codes(type_slug="service-urgences", care_levels=["secondary"]) == ["emergency_not_emergency"]
    assert codes(type_slug="service-urgences", care_levels=None) == ["emergency_not_emergency"]
    assert codes(type_slug="service-urgences", care_levels=["emergency"]) == []


@pytest.mark.parametrize(
    "type_slug, code, offer",
    [
        ("caarud", "caarud_without_harm_reduction", "harm_reduction"),
        ("centre-sante-sexuelle", "sexual_health_without_screening", "screening"),
        ("clinique-psychiatrique", "clinic_without_hospitalisation", "full_time_hospitalisation"),
        ("clinique-psychiatrique", "clinic_without_hospitalisation", "day_hospitalisation"),
        ("hopital-de-jour", "day_hospital_without_day_hospitalisation", "day_hospitalisation"),
        ("programme-etp", "etp_without_education", "therapeutic_education"),
    ],
)
def test_a_type_that_is_defined_by_what_it_does_offers_it(type_slug, code, offer):
    assert codes(type_slug=type_slug, offers=["consultation"]) == [code]
    assert codes(type_slug=type_slug, offers=[offer]) == []


def test_a_porteur_is_known_by_its_siren_and_is_not_listed_as_a_service():
    porteur = dict(type_slug="organisme-gestionnaire", siren="819903261", listed=False)
    assert codes(**porteur) == []
    assert codes(**{**porteur, "siren": None}) == ["porteur_without_siren"]
    assert codes(**{**porteur, "listed": True}) == ["porteur_listed"]


def test_an_unlisted_porteur_is_judged_by_the_porteur_rules_only():
    assert codes(type_slug="organisme-gestionnaire", listed=False, siren=None, description=None, phones=[],
                 offers=None) == ["porteur_without_siren"]


# --- by offer ------------------------------------------------------------------------


def test_a_day_hospital_offers_a_day_at_the_hospital_not_only_a_stay():
    assert codes(type_slug="hopital-de-jour", offers=["full_time_hospitalisation"]) == ["day_hospital_without_day_hospitalisation"]


@pytest.mark.parametrize("offer", ["full_time_hospitalisation", "day_hospitalisation", "screening"])
def test_an_offer_that_needs_a_place_is_not_offered_by_an_immaterial_entry(offer):
    assert "offer_needs_a_place" in codes(**{**LINE, "offers": [offer]})
    assert "offer_needs_a_place" not in codes(offers=[offer])


def test_training_needs_somewhere_to_find_the_sessions():
    assert codes(offers=["training"], websites=[]) == ["training_without_website"]
    assert codes(offers=["training"], websites=["https://x.fr"]) == []
    assert codes(offers=["listening"], websites=[]) == []


def test_the_severity_tells_what_is_missing_from_what_is_to_complete():
    by_code = {rule.code: rule.severity for rule in RULES}
    assert by_code["no_contact"] == "missing"
    assert by_code["line_without_phone"] == "missing"
    assert by_code["no_location"] == "missing"
    assert by_code["no_description"] == "incomplete"
    assert by_code["no_offers"] == "incomplete"


def test_the_problems_come_back_missing_first_then_in_the_order_of_the_catalogue():
    found = problems(healthy(phones=[], description=None, offers=None))
    assert [code for code, _ in found] == ["no_contact", "no_description", "no_offers"]
    assert [severity for _, severity in found] == ["missing", "incomplete", "incomplete"]
