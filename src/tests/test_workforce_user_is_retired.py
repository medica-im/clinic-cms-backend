"""The /api/v1/workforce/user/ route is gone, and stays gone.

Retired rather than ported. Nothing called it: the only mention of "workforce"
in the frontend was inside a commented-out block in sitemap.xml/+server.ts,
importing a `workforceStore` that no longer exists, and no request for the path
appears in the server logs. Its queryset was empty in any case — it reads
NetworkEdge, which has no rows.

It is worth a test rather than a silent deletion because of what the route was
holding up. WorkforceUserSerializer.get_appointments was the last reader of the
Postgres addressbook.Appointment table:

    for appointment in obj.user.contact.appointments.all():

Appointments moved to the graph — routers/appointment.py writes
directory.models.agraph.Appointment, and directory/utils reads it back — so
that table is residue. Re-adding a reader here would resurrect it, and the
reader would be a dormant one nobody exercises: the branch below it called
`self.create_appointment(self, id=...)`, passing self twice with a keyword the
method does not take, which no test and no request ever reached.

The occupation and dictionary routes of this app are deliberately untouched.
"""

import pytest
from django.urls import NoReverseMatch, resolve, reverse
from django.urls.exceptions import Resolver404


class TestTheRouteIsUnroutable:
    def test_the_url_does_not_resolve(self):
        with pytest.raises(Resolver404):
            resolve("/api/v1/workforce/user/")

    def test_the_detail_url_does_not_resolve(self):
        with pytest.raises(Resolver404):
            resolve("/api/v1/workforce/user/1/")

    @pytest.mark.parametrize("name", ["workforce:User-list", "workforce:User-detail"])
    def test_the_router_names_are_gone(self, name):
        """The DefaultRouter registration is removed, not merely unrouted."""
        with pytest.raises(NoReverseMatch):
            reverse(name)


class TestTheServerAgrees:
    """Resolution is one thing; what a client receives is another."""

    @pytest.mark.django_db
    def test_a_request_gets_404(self, client, settings):
        # The site middleware resolves a Site per request, and the test
        # database has none, so without this the request fails on the way in
        # and the 404 would not mean what it says.
        from django.contrib.sites.models import Site

        site = Site.objects.create(domain="testserver", name="testserver")
        settings.SITE_ID = site.pk

        assert client.get("/api/v1/workforce/user/").status_code == 404


class TestTheAppointmentReaderIsGone:
    """The point of the exercise: nothing in workforce reads the table.

    Asserted against the module rather than the route, because a serializer
    left behind would keep addressbook.Appointment alive even with the URL
    withdrawn — and the table cannot be dropped while a reader exists.
    """

    def test_the_serializer_is_removed(self):
        from workforce import serializers

        assert not hasattr(serializers, "WorkforceUserSerializer")

    def test_the_viewset_is_removed(self):
        from workforce import views

        assert not hasattr(views, "WorkforceUserViewSet")

    def test_workforce_does_not_import_the_appointment_model(self):
        """The import itself, so a new caller cannot appear quietly."""
        import inspect

        from workforce import serializers

        source = inspect.getsource(serializers)
        assert "Appointment" not in source, (
            "workforce.serializers references Appointment again: the Postgres "
            "addressbook.Appointment table has a reader once more, and it "
            "cannot be dropped until that is resolved"
        )

    def test_nothing_in_the_app_traverses_contact_appointments(self):
        """The related_name hop, wherever it might reappear in the app."""
        import pathlib

        import workforce

        # __path__, not __file__: this package resolves with __file__ None, so
        # pathlib.Path(workforce.__file__) raises before asserting anything.
        root = pathlib.Path(list(workforce.__path__)[0])
        offenders = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if "migrations" not in path.parts
            and "contact.appointments" in path.read_text()
        ]
        assert not offenders, (
            f"{offenders} still traverse contact.appointments, the Postgres "
            "table that appointments moved off"
        )
