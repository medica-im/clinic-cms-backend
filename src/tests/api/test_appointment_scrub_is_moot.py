"""The dropped Appointment model can no longer arm the scrub list.

The companion of tests/test_appointment_table_is_dropped.py, split from it
because api.utils imports fastapi, which the django test container does not
have. That file asserts the model is gone; this one asserts the consequence
that mattered.

api.utils.role_bearing_attributes derives the scrub list from the addressbook
models declaring a `roles` M2M. addressbook.Appointment declared one, so
"appointments" entered the list — while the dicts the graph produces have no
`roles` key at all. `process` then read item["roles"], raised KeyError, and
returned 500 for every /e/{slug} on every site.

With the model dropped the derivation cannot produce the key, which is a
stronger guarantee than the explicit exclusion it replaces.
"""

class TestNothingScrubsAppointments:
    """The connection between the dropped model and the outage.

    role_bearing_attributes reads the models that declare a `roles` M2M. With
    the model gone the derivation cannot produce "appointments" at all, which
    is a stronger guarantee than the explicit exclusion that replaced it.
    """

    def test_appointments_is_not_in_the_derived_scrub_list(self):
        from api.utils import role_bearing_attributes

        assert "appointments" not in role_bearing_attributes()

    def test_a_graph_appointment_survives_an_anonymous_scrub(self):
        """The live request that used to 500, end to end."""
        from api.utils import process, role_bearing_attributes

        entry = {
            "uid": "entry-uid-001",
            "access": "anonymous",
            # The shape directory.utils builds: no roles key, by design.
            "appointments": [
                {
                    "uid": "appointment-uid-1",
                    "entry": "entry-uid-001",
                    "url": "https://rdv.example.test/maurice",
                    "phone": None,
                    "location": "office",
                }
            ],
        }

        process(entry, "anonymous", role_bearing_attributes())

        assert len(entry["appointments"]) == 1


