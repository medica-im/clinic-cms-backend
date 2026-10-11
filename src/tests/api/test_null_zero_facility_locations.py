"""Facilities stored at 0/0 lose their point.

The facility forms used to send 0/0 when nobody placed the facility, and the
API stored it: a pin in the Gulf of Guinea. The API now stores no point instead
(test_facility_location_null.py); this is the one-off fix for what was already
written, run by a directory migration so every backend gets it on deploy.
"""
import importlib
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import migrations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


MIGRATION = "directory.migrations.0031_null_zero_facility_locations"


@pytest.fixture
def cleared(monkeypatch):
    """The cache endpoints cleared, without needing redis or Postgres."""
    import directory.graph_fixes as graph_fixes

    calls: list[str] = []
    monkeypatch.setattr(graph_fixes, "sync_clear_cache", calls.append)
    return calls


@pytest.fixture
async def seeded(neo4j_graph):
    """Three facilities at 0/0 among ones that must be left alone."""
    facilities = {
        "zero-1": "point({longitude: 0, latitude: 0})",
        "zero-2": "point({longitude: 0.0, latitude: 0.0})",
        "zero-3": "point({longitude: 0, latitude: 0, crs: 'wgs-84'})",
        "lyon": "point({longitude: 4.882709, latitude: 45.749014})",
        "near-zero": "point({longitude: 0.0001, latitude: 0})",
        "greenwich": "point({longitude: 0, latitude: 4.88})",
        "no-point": None,
    }
    for name, location in facilities.items():
        await neo4j_graph.cypher_query(
            "CREATE (f:Facility {uid: $uid, name: $name"
            + (f", location: {location}" if location else "")
            + "})",
            {"uid": uuid.uuid4().hex, "name": name},
        )
    return facilities


async def locations() -> dict[str, tuple[float, float] | None]:
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        "MATCH (f:Facility) RETURN f.name, f.location.x, f.location.y"
    )
    return {
        name: None if x is None else (x, y) for name, x, y in rows
    }


async def run_fix() -> int:
    from directory.graph_fixes import null_zero_facility_locations

    return await sync_to_async(null_zero_facility_locations)()


class TestTheFix:
    async def test_it_removes_the_point_from_every_zero_zero_facility(
        self, seeded, cleared
    ):
        assert await run_fix() == 3

        after = await locations()
        assert after["zero-1"] is None
        assert after["zero-2"] is None
        assert after["zero-3"] is None

    async def test_it_leaves_every_other_facility_alone(self, seeded, cleared):
        await run_fix()

        after = await locations()
        assert after["lyon"] == (4.882709, 45.749014)
        assert after["near-zero"] == (0.0001, 0.0)
        assert after["greenwich"] == (0.0, 4.88)
        assert after["no-point"] is None

    async def test_running_it_again_changes_nothing(self, seeded, cleared):
        await run_fix()
        assert await run_fix() == 0

    async def test_it_clears_every_payload_carrying_coordinates(
        self, seeded, cleared
    ):
        await run_fix()

        assert set(cleared) == {
            "v1:facilities", "v2:public/facilities", "v2:entries"
        }

    async def test_it_clears_no_cache_when_nothing_changed(
        self, neo4j_graph, cleared
    ):
        """Also what keeps a fresh test-database build away from the ORM."""
        assert await run_fix() == 0
        assert cleared == []


class TestTheMigration:
    """Runs on `migrate`, so every backend is fixed by its deploy."""

    def operation(self):
        module = importlib.import_module(MIGRATION)
        (operation,) = module.Migration.operations
        assert isinstance(operation, migrations.RunPython)
        return operation

    async def test_it_runs_the_fix(self, seeded, cleared):
        await sync_to_async(self.operation().code)(None, None)

        assert (await locations())["zero-1"] is None

    def test_reversing_it_is_a_no_op(self):
        """0/0 carried no information, so there is nothing to put back."""
        assert self.operation().reverse_code is migrations.RunPython.noop
