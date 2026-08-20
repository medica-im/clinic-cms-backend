"""The Postgres addressbook.Appointment model is gone, and stays gone.

Appointments live on the graph. routers/appointment.py writes
directory.models.agraph.Appointment, directory/utils reads it back through
appointments_from_neomodel, and the payload a client receives is built from the
node — see tests/api/test_appointments_in_the_payload.py.

The Postgres table was residue from before that move: 66 rows against 101
nodes, last written by the retired transfer_appointments command. Its last
reader, workforce's WorkforceUserSerializer.get_appointments, went with the
/api/v1/workforce/user/ endpoint (tests/test_workforce_user_is_retired.py).

The scrub half of this — that the derivation can no longer produce
"appointments" at all — lives in tests/api/test_appointment_scrub_is_moot.py,
because api.utils imports fastapi and this file runs in the django container.

It is worth pinning rather than deleting quietly because the model's stray
`roles` M2M is what caused an outage. api.utils.role_bearing_attributes derives
the scrub list from the addressbook models that declare `roles`, so this model
put "appointments" in it — and the dicts the graph produces have no `roles`
key, so `process` raised KeyError and every /e/{slug} on every site returned
500. Re-adding this model re-arms exactly that trap.
"""

import pytest


class TestTheModelIsGone:
    def test_addressbook_has_no_appointment_model(self):
        from addressbook import models

        assert not hasattr(models, "Appointment"), (
            "addressbook.Appointment is back: appointments live on the graph, "
            "and this model's `roles` M2M re-arms the KeyError that took the "
            "public site down (see api.utils.role_bearing_attributes)"
        )

    def test_the_app_registry_does_not_know_it(self):
        """The registry, not just the module: a model can be defined elsewhere."""
        from django.apps import apps

        names = {model.__name__ for model in apps.get_app_config("addressbook").get_models()}
        assert "Appointment" not in names

    def test_the_table_does_not_exist(self, django_db_setup, db):
        from django.db import connection

        assert "addressbook_appointment" not in connection.introspection.table_names()

    def test_a_contact_has_no_appointments_relation(self):
        """The related_name the retired workforce serializer traversed."""
        from addressbook.models import Contact

        related = {f.get_accessor_name() for f in Contact._meta.related_objects}
        assert "appointments" not in related


class TestTheEditingSurfacesAreGone:
    def test_the_admin_does_not_register_it(self):
        from django.contrib import admin

        registered = {model.__name__ for model in admin.site._registry}
        assert "Appointment" not in registered

    def test_no_serializer_binds_it(self):
        """A Meta.model binding would keep the class alive by reference."""
        from addressbook.api import serializers

        assert not hasattr(serializers, "AppointmentSerializer")
