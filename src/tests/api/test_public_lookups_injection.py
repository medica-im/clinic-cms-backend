"""Lookups that anonymous callers reach take their values as Cypher parameters.

/communes, /departments, /effector-types, /organization-types, /effectors,
/facilities, /facilities-slug and /fullentries answer without a login and pass
path and query-string values to these functions. Spliced into the query text,
a value holding a double quote closed the string and the rest of it ran as
Cypher, writes included.

Every value in this graph holds a double quote, so a lookup finds its node
only if the value reaches Neo4j as a parameter: spliced in, it is a syntax
error, or worse.
"""

import pytest
from asgiref.sync import sync_to_async
from neomodel import adb

from api.serializers.effector import get_effectors
from api.serializers.effector_type import get_effector_types
from api.serializers.facility import async_get_facilities, get_facilities
from api.serializers.geography import get_communes, get_departments
from api.serializers.organization import get_organization_types
from directory.utils import async_find_entry, find_entry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

Q = 'o"quote'
# Entry uids are also Postgres UUIDs (the entry's Contact row), so this one is
# real hex; the entry lookup is probed with a quoted uid that matches nothing.
ENTRY = "e" * 32


@pytest.fixture
async def graph(neo4j_graph):
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: 'fr', name_fr: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: $q, name: 'Rhône', code: $q, slug: 'rhone', wikidata: 'Q46130'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: $q, name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (f:Facility {uid: $q, slug: $q, name: 'Cabinet Lafayette'})
        CREATE (et:EffectorType {uid: $q, name_fr: 'infirmier', label_fr: 'infirmier', synonyms_fr: [],
                                 definition_fr: '', slug_fr: 'infirmier'})
        CREATE (e:Effector {uid: $q, name_fr: 'Jean Dupont', creator_directory: $q})
        CREATE (u:User {uid: $q})
        CREATE (d:Directory {name: $q})
        CREATE (entry:Entry {uid: $q, slug: 'dupont-jean-infirmier-lyon', active: true})
        CREATE (:OrganizationType {uid: $q, name: 'CPTS', name_fr: 'CPTS', label_fr: 'CPTS'})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (e)-[:OWNED_BY]->(u)
        CREATE (d)-[:HAS_ENTRY]->(entry)
        CREATE (entry)-[:HAS_FACILITY]->(f), (entry)-[:HAS_EFFECTOR]->(e), (entry)-[:HAS_EFFECTOR_TYPE]->(et)
        """,
        {"q": Q},
    )


@pytest.fixture
async def entry_graph(neo4j_graph):
    """An entry whose every node has a hex uid: the entry page reads their
    contact details from Postgres, keyed by UUID."""
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: $country, name_fr: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: $dpt, name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q46130'})
        CREATE (c:AdministrativeTerritorialEntityOfFrance:Commune {uid: $commune, name_fr: 'Lyon', slug_fr: 'lyon'})
        CREATE (f:Facility {uid: $facility, slug: 'cabinet-lafayette', name: 'Cabinet Lafayette'})
        CREATE (et:EffectorType {uid: $type, name_fr: 'infirmier', label_fr: 'infirmier', synonyms_fr: [],
                                 definition_fr: '', slug_fr: 'infirmier'})
        CREATE (e:Effector {uid: $effector, name_fr: 'Jean Dupont', creator_directory: 'test'})
        CREATE (d:Directory {name: 'test'})
        CREATE (entry:Entry {uid: $entry, slug: 'dupont-jean-infirmier-lyon', active: true})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (d)-[:HAS_ENTRY]->(entry)
        CREATE (entry)-[:HAS_FACILITY]->(f), (entry)-[:HAS_EFFECTOR]->(e), (entry)-[:HAS_EFFECTOR_TYPE]->(et)
        """,
        {"entry": ENTRY, "country": "1" * 32, "dpt": "2" * 32, "commune": "3" * 32, "facility": "4" * 32, "type": "5" * 32,
         "effector": "6" * 32},
    )


def uids(items):
    return [item.uid for item in items]


async def test_communes_by_uid(graph):
    assert uids(get_communes(uid=Q)) == [Q]


async def test_communes_by_department(graph):
    assert uids(get_communes(department=Q)) == [Q]


async def test_departments_by_uid(graph):
    assert uids(get_departments(uid=Q)) == [Q]


async def test_effector_types_by_uid(graph):
    assert uids(get_effector_types(uid=Q)) == [Q]


async def test_organization_types_by_uid(graph):
    assert uids(get_organization_types(uid=Q)) == [Q]


@pytest.mark.parametrize(
    "criterion",
    ["uid", "owner", "effector_type", "facility", "commune", "department_of_france", "directory"],
)
async def test_effectors_by_each_criterion(graph, criterion):
    assert uids(get_effectors(**{criterion: Q})) == [Q]


@pytest.mark.parametrize("criterion", ["uid", "slug", "directory"])
async def test_facilities_by_each_criterion(graph, criterion):
    assert uids(await async_get_facilities(**{criterion: Q})) == [Q]


@pytest.mark.parametrize("criterion", ["uid", "directory"])
async def test_facilities_by_each_criterion_sync(graph, criterion):
    assert uids(get_facilities(**{criterion: Q})) == [Q]


async def test_entry_by_uid(entry_graph):
    assert (await async_find_entry(uid=ENTRY))["entry"].uid == ENTRY


async def test_entry_by_a_quoted_uid_is_not_found(entry_graph):
    assert not await async_find_entry(uid=Q)


async def test_entry_by_uid_sync(entry_graph):
    assert (await sync_to_async(find_entry)(uid=ENTRY))["entry"].uid == ENTRY


async def test_entry_by_a_quoted_uid_is_not_found_sync(entry_graph):
    assert not await sync_to_async(find_entry)(uid=Q)
