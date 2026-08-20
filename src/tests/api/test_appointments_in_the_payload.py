"""What appointments look like by the time a client receives them.

The write path is covered by test_appointments.py. This file covers the read
path, which had no tests at all and is where the outage came from.

An appointment is public and lives on the graph. That combination is the whole
point of this file:

  * public          -> it must survive `process` for an anonymous viewer.
  * on the graph    -> the dict is built by directory.utils from a node, not
                       from the Postgres row, so it has no `roles` key.

The Postgres addressbook.Appointment model does declare a `roles` M2M, and
deriving the scrub list from the models alone therefore swept `appointments`
into it. `process` then read item["roles"] on a dict that has never had one,
raised KeyError, and returned 500 for every /e/{slug} on the site — the public
directory, not merely an admin corner.

Every existing scrubbing test built its items with a helper that always
supplies `roles`, so none of them could reproduce it. These build the dict the
way the application does.
"""

import pytest

from directory.utils import appointments_from_neomodel


ENTRY_UID = "entry-uid-001"


class GraphAppointment:
    """A stand-in for a neomodel Appointment node.

    Not tests.conftest.FakeNode: that one's `labels()` is a coroutine, which
    suits the async serializer, while `appointments_from_neomodel` is the sync
    one and calls `node.labels()` directly. Giving it an awaitable there yields
    a coroutine object that no branch matches, so every location silently
    becomes None — a fake that lies in exactly the direction these tests exist
    to catch.
    """

    def __init__(self, uid, url, phone, labels):
        self.uid = uid
        self.url = url
        self.phone = phone
        self._labels = labels

    def labels(self):
        return self._labels


def office(**overrides) -> GraphAppointment:
    props = {
        "uid": "appointment-uid-office",
        "url": "https://rdv.example.test/office",
        "phone": None,
        "labels": ["Appointment", "Office"],
    }
    props.update(overrides)
    return GraphAppointment(**props)


def house_call(**overrides) -> GraphAppointment:
    props = {
        "uid": "appointment-uid-housecall",
        "url": None,
        "phone": "+33412345678",
        "labels": ["Appointment", "HouseCall"],
    }
    props.update(overrides)
    return GraphAppointment(**props)


def unplaced(**overrides) -> GraphAppointment:
    """An appointment with neither Office nor HouseCall: location is None."""
    props = {
        "uid": "appointment-uid-unplaced",
        "url": "https://rdv.example.test/anywhere",
        "phone": None,
        "labels": ["Appointment"],
    }
    props.update(overrides)
    return GraphAppointment(**props)


class TestTheShapeTheSerializerProduces:
    """The dict the graph yields, field by field.

    These assertions are what api.utils.role_bearing_attributes has to agree
    with. If a `roles` key ever appears here, the exclusion of Appointment in
    that function becomes wrong and should be revisited — and the assertion
    below will say so rather than letting it drift.
    """

    def test_an_appointment_carries_no_roles_key(self):
        """The fact the whole outage turned on."""
        [appointment] = appointments_from_neomodel(ENTRY_UID, [office()])

        assert "roles" not in appointment, (
            "the serialised appointment now has a roles key: "
            "api.utils.role_bearing_attributes excludes Appointment on the "
            "grounds that it has none, and that exclusion needs revisiting"
        )

    def test_the_fields_are_exactly_the_documented_five(self):
        [appointment] = appointments_from_neomodel(ENTRY_UID, [office()])

        assert set(appointment) == {"uid", "entry", "url", "phone", "location"}

    def test_the_entry_uid_is_threaded_through(self):
        [appointment] = appointments_from_neomodel(ENTRY_UID, [office()])

        assert appointment["entry"] == ENTRY_UID


class TestLocationComesFromTheLabels:
    """location is not a property: it is derived from the node's extra label."""

    def test_an_office_appointment(self):
        [appointment] = appointments_from_neomodel(ENTRY_UID, [office()])

        assert appointment["location"] == "office"
        assert appointment["url"] == "https://rdv.example.test/office"
        assert appointment["phone"] is None

    def test_a_house_call_appointment(self):
        [appointment] = appointments_from_neomodel(ENTRY_UID, [house_call()])

        assert appointment["location"] == "house_call"
        assert appointment["phone"] == "+33412345678"
        assert appointment["url"] is None

    def test_an_appointment_with_neither_label(self):
        [appointment] = appointments_from_neomodel(ENTRY_UID, [unplaced()])

        assert appointment["location"] is None

    def test_several_appointments_keep_their_own_locations(self):
        """One entry commonly offers both, and they must not be conflated."""
        result = appointments_from_neomodel(ENTRY_UID, [office(), house_call()])

        assert [a["location"] for a in result] == ["office", "house_call"]


class TestTheEmptyCases:
    """No appointments is normal — most entries have none."""

    @pytest.mark.parametrize("empty", [None, [], [[]]], ids=["none", "empty", "nested-empty"])
    def test_nothing_yields_none(self, empty):
        assert appointments_from_neomodel(ENTRY_UID, empty) is None

    def test_a_bare_node_is_wrapped_rather_than_iterated(self):
        """Callers pass either a node or a list, so a bare node is wrapped.

        Asserted on the source rather than by calling it. The wrapping is a
        `type(nodes) in [Appointment, Office, HouseCall]` check against the
        real neomodel classes, so a stand-in node is not recognised and would
        skip the branch, while a real one cannot reach `labels()` without a
        database — `ValueError: Can't run cypher operation on unsaved node`.
        Neither route tests the branch, so this pins the check itself: without
        it a bare node falls into the comprehension and iterates a node object.
        """
        import ast
        import inspect

        import directory.utils

        source = inspect.getsource(directory.utils.appointments_from_neomodel)
        tree = ast.parse(source.lstrip())

        wrapped = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and isinstance(node.ops[0], ast.In)
            and isinstance(node.left, ast.Call)
            and getattr(node.left.func, "id", None) == "type"
        ]
        assert wrapped, (
            "appointments_from_neomodel no longer wraps a single node: a "
            "caller passing one node instead of a list will iterate the node"
        )
        [names] = [
            [getattr(e, "id", None) for e in node.comparators[0].elts]
            for node in wrapped
        ]
        assert set(names) == {"Appointment", "Office", "HouseCall"}, (
            f"the wrap accepts {names}: a subclass added to the graph must be "
            "listed here or a bare node of it will be iterated"
        )


class TestAPublicAppointmentReachesEveryone:
    """The end the user cares about: scrubbing must not touch appointments.

    This is the assertion that would have failed before the fix, in the same
    shape as the live request: build the payload the way directory.utils does,
    then run it through the scrub the routers run.
    """

    @pytest.mark.parametrize(
        "role", ["anonymous", "registered", "staff", "administrator", "superuser"]
    )
    def test_every_viewer_sees_the_appointment(self, role):
        from api.utils import process, role_bearing_attributes

        appointments = appointments_from_neomodel(
            ENTRY_UID, [office(), house_call()]
        )
        entry = {
            "uid": ENTRY_UID,
            "name": "Maurice Dantec",
            "access": "anonymous",
            "appointments": [dict(a) for a in appointments],
        }

        # The call the routers make. Before the fix this raised KeyError.
        process(entry, role, role_bearing_attributes())

        assert len(entry["appointments"]) == 2, (
            f"a {role} viewer lost a public appointment to the scrub"
        )
        assert [a["location"] for a in entry["appointments"]] == [
            "office",
            "house_call",
        ]
