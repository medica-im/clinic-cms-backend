"""What a request to create or change an entry must say before it is looked at.

Rules checked here need no database; whether a person or a place already exists
is for preflight. They are the ones the user decided: a name longer than 40
characters needs a shorter label, a physical person has a gender, an
organisation does not, and an entry is in at least one directory.
"""
import pytest
from pydantic import ValidationError

from api.types.entry_request import CreateEntryOp, FacilitySpec, LABEL_MAX, PersonSpec, UpdateEntryOp

LONG = "x" * (LABEL_MAX + 1)
EXACT = "x" * LABEL_MAX

PLACE = {"name": "Cabinet Test", "department": "69", "commune": "Lyon"}


def create(**over):
    base = {
        "type": "infirmier",
        "directories": ["Lyon 3"],
        "person": {"kind": "person", "name": "Jean Dupont", "gender": "M"},
        "facility": PLACE,
    }
    return CreateEntryOp(**{**base, **over})


class TestTheLabelRule:
    def test_a_name_of_40_characters_needs_no_label(self):
        assert PersonSpec(kind="organisation", name=EXACT).label is None

    def test_a_longer_name_needs_a_label(self):
        with pytest.raises(ValidationError, match="label"):
            PersonSpec(kind="organisation", name=LONG)

    def test_a_longer_name_with_a_short_label_is_fine(self):
        assert PersonSpec(kind="organisation", name=LONG, label="Court").label == "Court"

    def test_a_label_may_not_be_longer_than_40(self):
        with pytest.raises(ValidationError, match="label"):
            PersonSpec(kind="organisation", name="Court", label=LONG)

    def test_the_rule_is_the_same_for_a_facility(self):
        with pytest.raises(ValidationError, match="label"):
            FacilitySpec(name=LONG, department="69", commune="Lyon")
        assert FacilitySpec(name=LONG, label="Court", department="69", commune="Lyon").label == "Court"

    def test_a_blank_label_counts_as_none(self):
        with pytest.raises(ValidationError, match="label"):
            PersonSpec(kind="organisation", name=LONG, label="  ")


class TestAPerson:
    def test_a_physical_person_has_a_gender(self):
        with pytest.raises(ValidationError, match="gender"):
            PersonSpec(kind="person", name="Jean Dupont")

    def test_an_organisation_has_none(self):
        with pytest.raises(ValidationError, match="gender"):
            PersonSpec(kind="organisation", name="URPS médecins", gender="N")

    def test_the_kind_is_one_of_two(self):
        with pytest.raises(ValidationError):
            PersonSpec(kind="robot", name="R2")

    def test_rpps_is_eleven_digits(self):
        with pytest.raises(ValidationError):
            PersonSpec(kind="person", name="Jean Dupont", gender="M", rpps=123)

    def test_names_are_trimmed_and_not_blank(self):
        assert PersonSpec(kind="organisation", name="  URPS  ").name == "URPS"
        with pytest.raises(ValidationError):
            PersonSpec(kind="organisation", name="   ")


class TestCreating:
    def test_a_complete_request_is_valid(self):
        assert create().type == "infirmier"

    def test_an_entry_is_in_at_least_one_directory(self):
        with pytest.raises(ValidationError, match="directories"):
            create(directories=[])

    def test_a_facility_names_its_department_and_commune(self):
        with pytest.raises(ValidationError):
            create(facility={"name": "Cabinet Test"})

    def test_the_access_level_defaults_to_anonymous(self):
        assert create().access == "anonymous"

    def test_nothing_unknown_is_accepted(self):
        with pytest.raises(ValidationError):
            create(colour="blue")


class TestUpdating:
    def test_a_request_without_a_change_is_refused(self):
        with pytest.raises(ValidationError, match="nothing to change"):
            UpdateEntryOp(entry="some-slug")

    def test_a_label_change_is_enough(self):
        op = UpdateEntryOp(entry="some-slug", person={"label": "Court"})
        assert op.person.label == "Court"

    def test_a_directory_cannot_be_added_and_removed_at_once(self):
        with pytest.raises(ValidationError, match="Lyon 3"):
            UpdateEntryOp(entry="some-slug", directories={"add": ["Lyon 3"], "remove": ["Lyon 3"]})

    def test_a_new_long_name_needs_its_label_in_the_same_request(self):
        with pytest.raises(ValidationError, match="label"):
            UpdateEntryOp(entry="some-slug", facility={"name": LONG})
        UpdateEntryOp(entry="some-slug", facility={"name": LONG, "label": "Court"})

    def test_a_move_names_the_new_place_in_full(self):
        op = UpdateEntryOp(entry="some-slug", move_to=PLACE)
        assert op.move_to.commune == "Lyon"
