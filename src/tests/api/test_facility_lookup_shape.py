"""What the facility lookups return as a facility's effectors.

The queries collect "name (type)" for each entry at the facility. neomodel 5
handed that list back wrapped in one more list, which the code unwrapped
(`[effectors]`, `effectors[0]`); neomodel 6 hands it back as Cypher built it.
Either way a facility's effectors must be a flat list of labels, empty when
nobody works there.
"""

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from api.serializers.facility import async_get_facilities, get_facilities

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BUSY, EMPTY = "b" * 32, "a" * 32


@pytest.fixture
async def facilities(neo4j_graph):
    await adb.cypher_query(
        """
        CREATE (dpt:DepartmentOfFrance {uid: '2', name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q46130'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: '3', name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (busy:Facility {uid: $busy, slug: 'cabinet-lafayette', name: 'Cabinet Lafayette'})
        CREATE (empty:Facility {uid: $empty, slug: 'local-vide', name: 'Local vide'})
        CREATE (busy)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (empty)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (nurse:EffectorType {uid: 'n', name_fr: 'infirmier'}), (gp:EffectorType {uid: 'g', name_fr: 'médecin'})
        CREATE (:Effector {uid: 'jean', name_fr: 'Jean Dupont'})<-[:HAS_EFFECTOR]-(e1:Entry {uid: 'e1'})
        CREATE (:Effector {uid: 'anne', name_fr: 'Anne Martin'})<-[:HAS_EFFECTOR]-(e2:Entry {uid: 'e2'})
        CREATE (e1)-[:HAS_FACILITY]->(busy), (e1)-[:HAS_EFFECTOR_TYPE]->(nurse)
        CREATE (e2)-[:HAS_FACILITY]->(busy), (e2)-[:HAS_EFFECTOR_TYPE]->(gp)
        """,
        {"busy": BUSY, "empty": EMPTY},
    )


BUSY_EFFECTORS = ["Anne Martin (médecin)", "Jean Dupont (infirmier)"]


async def test_a_busy_facility_lists_each_effector(facilities):
    [facility] = await async_get_facilities(uid=BUSY)
    assert sorted(facility.effectors) == BUSY_EFFECTORS


async def test_an_empty_facility_lists_no_effector(facilities):
    [facility] = await async_get_facilities(uid=EMPTY)
    assert facility.effectors == []


async def test_a_busy_facility_lists_each_effector_sync(facilities):
    [facility] = await sync_to_async(get_facilities)(uid=BUSY)
    assert sorted(facility.effectors) == BUSY_EFFECTORS


async def test_an_empty_facility_lists_no_effector_sync(facilities):
    [facility] = await sync_to_async(get_facilities)(uid=EMPTY)
    assert facility.effectors == []
