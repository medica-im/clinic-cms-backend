"""The slug lookups behind /slugfullentries and /ftefullentries.

Both routes answer anonymous callers, and their path segments reach Cypher.
Spliced into the query text, a segment holding a double quote closed the
string and the rest of it ran as Cypher: reading any entry, or writing to the
graph. As parameters, a segment is only ever a value to compare.

The injection probes here only widen a match (`" OR "a"="a`), so a failure
shows up as an entry found where none should be, and nothing is written.
"""

import pytest
from fastapi import HTTPException
from neomodel import adb

from api.serializers.slug_fullentry import query_find_entry, slug_find_entry

ACTIVE, INACTIVE = "a" * 32, "b" * 32
WIDEN = 'nope" OR "a"="a'


@pytest.fixture
async def entries(neo4j_graph):
    """Two entries at one place of Lyon 3e: an active nurse, an inactive GP."""
    await adb.cypher_query(
        """
        CREATE (c:Commune {slug_fr: 'lyon-3e'})
        CREATE (f:Facility {slug: 'cabinet-lafayette'})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (nurse:EffectorType {slug_fr: 'infirmier'}), (gp:EffectorType {slug_fr: 'medecin-generaliste'})
        CREATE (jean:Effector {slug_fr: 'dupont-jean'}), (anne:Effector {slug_fr: 'martin-anne'})
        CREATE (:Entry {uid: $active, active: true})-[:HAS_FACILITY]->(f)
        CREATE (:Entry {uid: $inactive, active: false})-[:HAS_FACILITY]->(f)
        WITH nurse, gp, jean, anne
        MATCH (a:Entry {uid: $active}), (i:Entry {uid: $inactive})
        CREATE (a)-[:HAS_EFFECTOR]->(jean), (a)-[:HAS_EFFECTOR_TYPE]->(nurse)
        CREATE (i)-[:HAS_EFFECTOR]->(anne), (i)-[:HAS_EFFECTOR_TYPE]->(gp)
        """,
        {"active": ACTIVE, "inactive": INACTIVE},
    )


def assert_not_found(exc_info):
    assert exc_info.value.status_code == 404


@pytest.mark.integration
class TestSlugFindEntry:
    async def test_finds_the_entry_by_commune_person_and_type(self, entries):
        assert await slug_find_entry("lyon-3e", "dupont-jean", "infirmier") == ACTIVE

    async def test_an_inactive_entry_is_not_found_by_default(self, entries):
        with pytest.raises(HTTPException) as exc_info:
            await slug_find_entry("lyon-3e", "martin-anne", "medecin-generaliste")
        assert_not_found(exc_info)

    async def test_an_inactive_entry_is_found_when_activity_is_not_asked(self, entries):
        """/slugfullentries passes active=None: old links to inactive entries still resolve."""
        assert await slug_find_entry("lyon-3e", "martin-anne", "medecin-generaliste", None) == INACTIVE

    async def test_an_unknown_slug_is_not_found(self, entries):
        with pytest.raises(HTTPException) as exc_info:
            await slug_find_entry("lyon-3e", "dupont-jean", "kinesitherapeute")
        assert_not_found(exc_info)

    @pytest.mark.parametrize("field", ["commune", "effector", "type"])
    async def test_a_quote_in_a_segment_is_part_of_the_value(self, entries, field):
        segments = {"commune": "lyon-3e", "effector": "dupont-jean", "type": "infirmier", field: WIDEN}
        with pytest.raises(HTTPException) as exc_info:
            await slug_find_entry(**segments, active=None)
        assert_not_found(exc_info)


@pytest.mark.integration
class TestQueryFindEntry:
    async def test_finds_the_entry_by_place_person_and_type(self, entries):
        assert await query_find_entry("dupont-jean", "cabinet-lafayette", "infirmier") == ACTIVE

    async def test_an_inactive_entry_is_not_found(self, entries):
        with pytest.raises(HTTPException) as exc_info:
            await query_find_entry("martin-anne", "cabinet-lafayette", "medecin-generaliste")
        assert_not_found(exc_info)

    @pytest.mark.parametrize("field", ["effector", "facility", "type"])
    async def test_a_quote_in_a_segment_is_part_of_the_value(self, entries, field):
        segments = {"effector": "dupont-jean", "facility": "cabinet-lafayette", "type": "infirmier", field: WIDEN}
        with pytest.raises(HTTPException) as exc_info:
            await query_find_entry(**segments)
        assert_not_found(exc_info)


@pytest.mark.no_db
def test_the_unused_query_route_is_gone():
    """/queryfullentries took the same three values from the query string; nothing called it."""
    from main import app

    assert "/queryfullentries/" not in {route.path for route in app.routes}
