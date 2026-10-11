"""Lookups fed by the system take their values as Cypher parameters too.

These are not reachable anonymously: the values come from site configuration
(directory names), from the graph (situation, effector, facility uids) or from
the Django admin. Spliced into the query text, a double quote in any of them
still closed the string and ran the rest as Cypher. Every value here holds
one, so a lookup finds its node only if the value is a parameter.
"""

from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from api.serializers.entries import get_entries as entry_uids_for
from directory.utils import async_entries_of_situation, contact_uids, get_entries

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

Q = 'o"quote'
DIRECTORY = SimpleNamespace(name=Q)
# The listing reads the entry's avatar from Postgres, keyed by UUID.
ENTRY, EFFECTOR, FACILITY, LOCATION = "e" * 32, "7" * 32, "4" * 32, "9" * 32


@pytest.fixture
async def graph(neo4j_graph):
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: '1', name_fr: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: '2', name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q46130'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: '3', name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (f:Facility {uid: $facility, slug: 'cabinet', name: 'Cabinet'})
        CREATE (et:EffectorType {uid: $q, name_fr: 'infirmier', slug_fr: 'infirmier'})
        CREATE (e:Effector {uid: $effector, name_fr: 'Jean o"quote', creator_directory: $q})
        CREATE (entry:Entry {uid: $entry, slug: 'jean-infirmier', active: true})
        CREATE (d:Directory {name: $q})
        CREATE (s:Situation {uid: $q})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (entry)-[:HAS_FACILITY]->(f), (entry)-[:HAS_EFFECTOR]->(e), (entry)-[:HAS_EFFECTOR_TYPE]->(et)
        CREATE (d)-[:HAS_ENTRY]->(entry)
        CREATE (e)-[:LOCATION {uid: $location}]->(f)
        CREATE (e)-[:IS_A]->(et), (et)-[:MANAGES]->(s)
        """,
        {"q": Q, "entry": ENTRY, "effector": EFFECTOR, "facility": FACILITY, "location": LOCATION},
    )


async def test_the_admins_contacts_of_a_directory(graph):
    assert await sync_to_async(contact_uids)(directory=DIRECTORY) == [EFFECTOR, LOCATION, FACILITY]


async def test_the_admins_contacts_by_name(graph):
    assert await sync_to_async(contact_uids)(directory=DIRECTORY, search='o"q') == [EFFECTOR, LOCATION, FACILITY]


async def test_a_search_is_text_not_a_pattern(graph):
    """`.*` would match every name if it reached the regex as a pattern."""
    assert not await sync_to_async(contact_uids)(directory=DIRECTORY, search=".*")


async def test_the_entries_of_a_situation(graph):
    assert await async_entries_of_situation(DIRECTORY, SimpleNamespace(uid=Q)) == [ENTRY]


async def test_the_entries_of_a_directory(graph):
    assert [row["entry"].uid for row in await get_entries(DIRECTORY)] == [ENTRY]


async def test_the_entries_of_a_directory_whatever_their_activity(graph):
    assert [row["entry"].uid for row in await get_entries(DIRECTORY, active=None)] == [ENTRY]


async def test_an_entry_by_its_person_place_and_type(graph):
    found = await sync_to_async(entry_uids_for)(effector=EFFECTOR, facility=FACILITY, effector_type=Q)
    assert found == [ENTRY]


async def test_an_entry_by_its_place_and_type(graph):
    assert await sync_to_async(entry_uids_for)(facility=FACILITY, effector_type=Q) == [ENTRY]


async def test_a_contact_change_stamps_its_facility(graph):
    """The uid is parsed as a UUID before any query: this one only pins the result."""
    import uuid

    from directory.timestamp import update_contact_timestamp

    await sync_to_async(update_contact_timestamp)(uuid.UUID(FACILITY))
    rows, _ = await adb.cypher_query("MATCH (f:Facility {uid: $uid}) RETURN f.contactUpdatedAt", {"uid": FACILITY})
    assert rows[0][0] is not None
