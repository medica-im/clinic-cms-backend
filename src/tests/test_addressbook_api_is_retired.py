"""The /api/v1/addressbook/ mount is gone, and stays gone.

The legacy Django profile API (list/create and detail/update/delete of social
profiles) served an empty table: addressbook_profile has no rows on production
or on annuaire.medica.im, and the frontend and the console never called it.
No v2 route writes a profile either: the model went too
(tests/test_profile_table_is_dropped.py).

The serializers stay: directory, facility and the v2 routers import from
addressbook.api.serializers. Only the HTTP surface is retired, so the modules
that served it must not come back unnoticed.
"""

import importlib.util

import pytest
from django.urls import resolve
from django.urls.exceptions import Resolver404


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/addressbook/",
        "/api/v1/addressbook/profile/",
        "/api/v1/addressbook/profile/1",
    ],
)
def test_the_url_does_not_resolve(path):
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.parametrize(
    "module", ["addressbook.api.urls", "addressbook.api.views", "addressbook.api.permissions"]
)
def test_the_module_that_served_it_is_removed(module):
    assert importlib.util.find_spec(module) is None


def test_the_serializers_other_apps_import_remain():
    from addressbook.api.serializers import ContactSerializer

    assert ContactSerializer
