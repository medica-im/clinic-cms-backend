"""The full entry serves the facility's stored values, so a clone copies them.

`facility.label` was served as « the label, or the name when there is none », a
display fallback. The clone wrote it back as the stored label, so the 60 santé mentale
facilities with an empty label on dev arrived on staging labelled with their name.
Every page that shows the label already falls back to the name itself.
"""
from types import SimpleNamespace

from api.serializers.fullentry import facility_resource


def facility(**over):
    return SimpleNamespace(**{"uid": "f1", "slug": "apsytude", "name": "Apsytude", "label": "", **over})


def test_an_empty_label_is_served_empty():
    assert facility_resource(facility())["label"] == ""


def test_no_label_is_served_as_none():
    assert facility_resource(facility(label=None))["label"] is None


def test_a_label_is_served_as_stored():
    assert facility_resource(facility(label="CMP Les Quadrilles"))["label"] == "CMP Les Quadrilles"


def test_the_siret_is_served_so_a_clone_keeps_it():
    assert facility_resource(facility(siret="13003075200013"))["siret"] == "13003075200013"


def test_a_facility_without_a_siret_serves_none():
    assert facility_resource(facility())["siret"] is None
