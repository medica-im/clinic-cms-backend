"""SIREN and SIRET: what an organization and its establishment are called by the State.

A SIREN (9 digits) names a legal unit, a SIRET (14 digits) one of its
establishments: the SIREN followed by a 5-digit NIC. Both end in a Luhn check
digit. That is what makes the rule the directory relies on checkable: an
establishment's SIRET starts with the SIREN of the legal unit that runs it.
The real MGEN numbers below come from the public register (recherche-entreprises).
"""
import pytest

from directory.identifiers import is_siren, is_siret, normalize, siren_of

pytestmark = pytest.mark.no_db

MGEN_SIREN = "441921913"
MGEN_HEAD_OFFICE = "44192191300014"
MGEN_LYON = "44192191300212"


def test_the_real_mgen_numbers_are_valid():
    assert is_siren(MGEN_SIREN)
    assert is_siret(MGEN_HEAD_OFFICE)
    assert is_siret(MGEN_LYON)


def test_a_siret_starts_with_the_siren_of_its_legal_unit():
    assert siren_of(MGEN_LYON) == MGEN_SIREN
    assert siren_of(MGEN_HEAD_OFFICE) == MGEN_SIREN


@pytest.mark.parametrize("value", ["", "44192191", "4419219130", "441921914", "44192191a", "441 921 913", None])
def test_a_siren_must_be_nine_digits_with_the_right_check_digit(value):
    assert not is_siren(value)


@pytest.mark.parametrize("value", ["", "4419219130021", "441921913002120", "44192191300213", "4419219130021a", None])
def test_a_siret_must_be_fourteen_digits_with_the_right_check_digit(value):
    assert not is_siret(value)


def test_spaces_in_a_number_are_not_part_of_it():
    assert normalize("441 921 913") == "441921913"
    assert normalize(" 441 921 913 00212 ") == "44192191300212"
    assert is_siren(normalize("441 921 913"))


def test_nothing_is_nothing():
    assert normalize(None) is None
    assert normalize("  ") is None


def test_la_poste_establishments_follow_their_own_rule():
    # La Poste's SIREN 356000000 is an exception of the register: its SIRETs are
    # valid when their digits add up to a multiple of 5, not by the Luhn check.
    assert is_siret("35600000000001")
    assert not is_siret("35600000000002")


def test_siren_of_a_malformed_siret_is_none():
    assert siren_of("123") is None
    assert siren_of(None) is None
