"""The entry's last-modification date is the entry's own.

`updatedAt` on a serialised entry is computed as a max across several nodes,
and the Entry's own `updatedAt` — the field the APOC triggers maintain on every
property and relationship write — was not among them:

    max([effector.updatedAt, facility.contactUpdatedAt, entry.contactUpdatedAt])

`contactUpdatedAt` is 0 on every node in the graph, so the max collapsed to the
effector's timestamp. On this site that made 21 of 22 entries report a
modification date *earlier than their own creation date* — one of them
19/12/2023 for an entry created 10/06/2026. The administrative table put the
two columns side by side and the contradiction became visible; the public
addressbook had been showing the same wrong date for as long.

The Entry is the thing being listed, so its own stamp has to be in the max.
"""
import pytest

pytestmark = pytest.mark.django_db


class FakeNode:
    def __init__(self, **props):
        for k, v in props.items():
            setattr(self, k, v)


def compute(entry_updated, effector_updated, facility_contact=0, entry_contact=0):
    """The max as the serializers compute it."""
    from api.serializers.allentries import entry_updated_at

    return entry_updated_at(
        entry=FakeNode(updatedAt=entry_updated, contactUpdatedAt=entry_contact),
        effector=FakeNode(updatedAt=effector_updated),
        facility=FakeNode(contactUpdatedAt=facility_contact),
    )


class TestTheEntryStampCounts:
    def test_an_entry_edited_after_its_effector_reports_its_own_date(self):
        """The case that was wrong: the entry is newer than the effector."""
        assert compute(entry_updated=2_000, effector_updated=1_000) == 2_000

    def test_a_modification_is_never_older_than_the_creation(self):
        # Aglae Vallat: created 10/06/2026, reported as modified 19/12/2023,
        # because only the effector's stale stamp was consulted.
        created = 1_781_051_364_626
        entry_updated = 1_781_051_366_574
        effector_updated = 1_703_003_395_839

        assert compute(entry_updated, effector_updated) >= created

    def test_an_effector_edited_later_still_counts(self):
        """The effector carries the person's name, so its edits are the
        entry's edits too — this is a widening, not a replacement."""
        assert compute(entry_updated=1_000, effector_updated=2_000) == 2_000

    def test_contact_timestamps_still_count(self):
        assert compute(1_000, 1_000, facility_contact=5_000) == 5_000
        assert compute(1_000, 1_000, entry_contact=7_000) == 7_000

    def test_a_missing_stamp_is_not_an_error(self):
        """Nodes predating a field have None rather than 0."""
        assert compute(entry_updated=None, effector_updated=3_000) == 3_000
        assert compute(entry_updated=3_000, effector_updated=None) == 3_000


class TestTheSerializersCanActuallyCallIt:
    """The helper is reachable from the functions that use it.

    Every test above exercises `entry_updated_at` in isolation, and all of them
    passed while /api/v2/fullentries answered 500 for every request:
    fullentry.py called it with a bare `entry`, a name that does not exist in
    either of those two functions — they receive a `node` dict and read
    `node["entry"]`. A NameError in a code path no test enters is invisible.

    So this checks the wiring rather than the arithmetic: that each call site
    names variables its own scope defines. Importing the module would not catch
    it — the name is only resolved when the line runs — so the source is read
    instead.
    """

    @staticmethod
    def _names_used_by(function) -> set[str]:
        """Every bare name the function body binds or receives."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.arg):
                names.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
        return names

    @staticmethod
    def _first_argument_of_the_call(function) -> str | None:
        """The expression passed as `entry` to entry_updated_at."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "entry_updated_at"
                and node.args
            ):
                return ast.dump(node.args[0])
        return None

    @pytest.mark.parametrize(
        "module_name,function_name",
        [
            ("api.serializers.fullentry", "createEffectorRessource"),
            ("api.serializers.fullentry", "createFullEntryResource"),
            ("api.serializers.allentries", "createEntryResource"),
        ],
    )
    def test_the_entry_argument_is_a_name_the_function_has(
        self, module_name, function_name
    ):
        """A bare name passed to the helper must be one this scope defines.

        Parsed rather than string-matched: the first version of this test
        asserted that "node[" appeared somewhere on the line, which
        `node["facility"]` satisfied — so it passed with the bug reintroduced
        and proved nothing.
        """
        import importlib

        function = getattr(importlib.import_module(module_name), function_name)
        argument = self._first_argument_of_the_call(function)
        assert argument, f"{function_name} no longer calls entry_updated_at"

        # A subscript such as node["entry"] is always fine; a bare Name has to
        # be something the function actually binds.
        if argument.startswith("Name("):
            name = argument.split("id='")[1].split("'")[0]
            assert name in self._names_used_by(function), (
                f"{function_name} passes `{name}` to entry_updated_at, but that "
                "name is not defined in it — the call raises NameError at "
                "runtime and every unit test of the helper still passes"
            )
