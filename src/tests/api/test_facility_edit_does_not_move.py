"""Editing a facility corrects it; it never moves it.

Adding a name, fixing the spelling of the street or the GPS position are
corrections. A different postal code means a different place, and the entries,
the slug and every shared link were made for the old one: that is a move, which
belongs to a future moving process, not to the edit form.

This is a business invariant, not a permission (CLAUDE.md, rule 3): a superuser
is refused too, so it lives with the serializer and answers 409 Conflict.
"""
import pytest
from fastapi import HTTPException

from api.serializers.facility import assert_facility_stays_put


class TestAnEditDoesNotMoveTheFacility:
    def test_the_same_postal_code_is_an_edit(self):
        assert_facility_stays_put("69003", "69003")

    def test_a_different_postal_code_is_a_move_and_is_refused(self):
        with pytest.raises(HTTPException) as refused:
            assert_facility_stays_put("69003", "69007")
        assert refused.value.status_code == 409

    def test_surrounding_spaces_do_not_make_a_move(self):
        assert_facility_stays_put("69003", " 69003 ")

    @pytest.mark.parametrize("stored", [None, "", "  "])
    def test_a_facility_with_no_postal_code_may_be_given_one(self, stored):
        assert_facility_stays_put(stored, "69003")

    @pytest.mark.parametrize("sent", [None, ""])
    def test_a_postal_code_cannot_be_erased(self, sent):
        with pytest.raises(HTTPException) as refused:
            assert_facility_stays_put("69003", sent)
        assert refused.value.status_code == 409
