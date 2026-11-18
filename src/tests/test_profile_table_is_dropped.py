"""addressbook.Profile and its history table are dropped, and stay dropped.

A profile was a free-text blurb per contact, written through the retired
/api/v1/addressbook/profile/ route. addressbook_profile is empty on production
and on annuaire.medica.im; their history table holds nine rows, three profiles
created in 2022 and deleted on 2023-09-17. Nothing writes one any more, and the
frontend never read the `profile` key of the full-entry payload.

Pinned rather than deleted quietly because the model's `roles` M2M puts it in
api.utils.role_bearing_attributes, whose PAYLOAD_KEY refuses a role-bearing
model it does not know. Re-adding the model re-arms that error log, and the
payload key it once fed would come back with no one enforcing its roles.
"""

import pytest


class TestTheModelIsGone:
    def test_addressbook_has_no_profile_model(self):
        from addressbook import models

        assert not hasattr(models, "Profile"), (
            "addressbook.Profile is back: nothing writes or reads profiles any "
            "more, and its `roles` M2M needs a payload key in "
            "api.utils.role_bearing_attributes"
        )

    def test_the_app_registry_does_not_know_it_or_its_history(self):
        from django.apps import apps

        names = {model.__name__ for model in apps.get_app_config("addressbook").get_models()}
        assert not {"Profile", "HistoricalProfile"} & names

    @pytest.mark.parametrize("table", ["addressbook_profile", "addressbook_historicalprofile"])
    def test_the_table_does_not_exist(self, django_db_setup, db, table):
        from django.db import connection

        assert table not in connection.introspection.table_names()

    def test_a_contact_has_no_profile_relation(self):
        from addressbook.models import Contact

        related = {f.get_accessor_name() for f in Contact._meta.related_objects}
        assert "profile" not in related


class TestNothingBindsIt:
    def test_the_admin_does_not_register_it(self):
        from django.contrib import admin

        registered = {model.__name__ for model in admin.site._registry}
        assert not {"Profile", "HistoricalProfile"} & registered

    def test_no_serializer_binds_it(self):
        """A Meta.model binding would keep the class alive by reference."""
        from addressbook.api import serializers

        for name in ("ProfileSerializer", "AsyncProfileSerializer"):
            assert not hasattr(serializers, name)

    def test_the_entry_payload_readers_are_gone(self):
        from directory import utils

        for name in ("get_profile_neomodel", "async_get_profile_neomodel"):
            assert not hasattr(utils, name)

    def test_the_payload_type_has_no_profile(self):
        pytest.importorskip("fastapi")
        from api.types.fullentry import FullEntry

        assert "profile" not in FullEntry.model_fields

    def test_the_role_scrub_list_does_not_name_it(self):
        pytest.importorskip("fastapi")
        import inspect

        from api import utils

        assert '"Profile"' not in inspect.getsource(utils.role_bearing_attributes)
