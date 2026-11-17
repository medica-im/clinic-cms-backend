"""The /api/v1/workforce/ mount is gone, and stays gone.

The legacy Django workforce API (dictionary of labels, occupation list) read
the SQL NetworkNode/NetworkEdge tree, which the graph replaced. Nothing calls
it: the frontend and the console have no reference to it.

The app itself stays: facility's foreign keys point at its models and
access.utils uses workforce.utils.is_staff. Only the HTTP surface is retired,
so the modules that served it must not come back unnoticed.
"""

import importlib.util

import pytest
from django.urls import resolve
from django.urls.exceptions import Resolver404


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/workforce/",
        "/api/v1/workforce/dictionary/",
        "/api/v1/workforce/occupation/",
        "/api/v1/workforce/occupation/1/",
    ],
)
def test_the_url_does_not_resolve(path):
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.parametrize("module", ["workforce.urls", "workforce.views", "workforce.serializers"])
def test_the_module_that_served_it_is_removed(module):
    assert importlib.util.find_spec(module) is None


def test_nothing_in_the_app_traverses_contact_appointments():
    """Appointments moved to the graph; the Postgres addressbook.Appointment
    table has no reader left, and one reappearing here would stop it being
    dropped (tests/test_appointment_table_is_dropped.py).
    """
    import pathlib

    import workforce

    # __path__, not __file__: this package resolves with __file__ None.
    root = pathlib.Path(list(workforce.__path__)[0])
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "migrations" not in path.parts and "contact.appointments" in path.read_text()
    ]
    assert not offenders, f"{offenders} traverse contact.appointments again"
