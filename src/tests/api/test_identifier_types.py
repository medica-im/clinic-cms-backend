"""SIREN on an entry, SIRET on a facility: what the API accepts and returns.

Numbers are written with spaces on the register's own pages ("441 921 913"), so
the spaces are dropped before checking; a number that is not what it claims to be
(wrong length, wrong check digit) is refused rather than stored. Sent as null on
a patch, a number is removed; left out, it stays.
"""
import pytest
from pydantic import ValidationError

from api.types.entry import Entry, EntryPatch, EntryPost
from api.types.facility import FacilityPost, FacilityPut

pytestmark = pytest.mark.no_db

SIREN = "441921913"
SIRET = "44192191300212"

FACILITY = {
    "name": "MGEN Lyon", "label": "MGEN Lyon", "slug": None, "building": None, "street": "44 rue Feuillat",
    "geographical_complement": None, "zip": "69003", "ban_id": None, "ban_banId": None, "commune": "c",
}
ENTRY = {"effector": "e", "effector_type": "t", "facility": "f", "memberships": None}


@pytest.mark.parametrize("model", [FacilityPost, FacilityPut])
def test_a_facility_may_carry_the_siret_of_its_establishment(model):
    body = {k: v for k, v in FACILITY.items() if model is FacilityPost or k != "commune"}
    assert model(**body, siret=SIRET).siret == SIRET
    assert model(**body).siret is None


def test_the_spaces_of_a_siret_are_dropped():
    assert FacilityPost(**FACILITY, siret="441 921 913 00212").siret == SIRET


@pytest.mark.parametrize("siret", [SIREN, "44192191300213", "4419219130021", "abc"])
def test_a_siret_that_is_not_one_is_refused(siret):
    with pytest.raises(ValidationError):
        FacilityPost(**FACILITY, siret=siret)


def test_a_blank_siret_is_no_siret():
    assert FacilityPost(**FACILITY, siret="  ").siret is None


@pytest.mark.parametrize("model", [EntryPost, EntryPatch])
def test_an_entry_may_carry_the_siren_of_its_legal_unit(model):
    body = ENTRY if model is EntryPost else {}
    assert model(**body, siren=SIREN).siren == SIREN
    assert model(**body, siren="441 921 913").siren == SIREN


@pytest.mark.parametrize("siren", [SIRET, "441921914", "44192191", "x"])
def test_a_siren_that_is_not_one_is_refused(siren):
    with pytest.raises(ValidationError):
        EntryPatch(siren=siren)


def test_a_patch_removes_the_siren_when_it_says_null_and_leaves_it_when_silent():
    assert "siren" in EntryPatch(siren=None).model_fields_set
    assert "siren" not in EntryPatch(active=True).model_fields_set


def test_the_entry_returned_names_its_siren():
    assert "siren" in Entry.model_fields
