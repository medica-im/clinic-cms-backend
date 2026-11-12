"""(Directory)-[:LISTS_NEED]->(Need): what a directory lists.

The santé mentale directory holds porteurs that are not mental health actors (a
hospital, the DAC): they must exist so a service can say who runs it, but never
reach the list, the map, the counts or the sitemap. So listing is decided in the
backend query, next to `owner_listed`, and never in the browser. A directory with
no such edge lists all its entries, as before: no existing directory changes.

An entry is listed when it manages the Need or a descendant Need, or a Condition
or Situation that IMPACTS it directly or through its PART_OF parents, whether the
edge is on the entry or on its type (subtypes included). Real Neo4j.
"""
from types import SimpleNamespace

import pytest

from directory.utils import get_entries_query

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENTRIES = ["need", "subneed", "condition", "situation", "type", "porteur", "other-need"]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (country:Country {uid: 'fr'}), (dpt:DepartmentOfFrance {uid: 'd69'}), (commune:Commune {uid: 'lyon'})
        CREATE (commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (facility:Facility {uid: 'f1'})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(commune)

        CREATE (mental:Need {uid: 'n-sm', slug: 'sante-mentale'}), (psy:Need {uid: 'n-psy'}), (vivre:Need {uid: 'n-viv'})
        CREATE (psy)-[:PART_OF]->(mental)
        CREATE (chapter:Condition {uid: 'c-ch'}), (disorder:Condition {uid: 'c-di'})
        CREATE (disorder)-[:PART_OF]->(chapter), (chapter)-[:IMPACTS]->(mental)
        CREATE (crisis:Situation {uid: 's-cr'})-[:IMPACTS]->(mental)

        CREATE (et1:EffectorType {uid: 't1'}), (et2:EffectorType {uid: 't2'}), (plain:EffectorType {uid: 't0'})
        CREATE (et2)-[:IS_A]->(et1), (et1)-[:MANAGES]->(mental)

        CREATE (sm:Directory {name: 'sm'}), (open:Directory {name: 'open'})
        CREATE (sm)-[:LISTS_NEED]->(mental)
        """
    )
    for uid in ENTRIES + ["open-porteur"]:
        await neo4j_graph.cypher_query(
            """
            MATCH (f:Facility {uid: 'f1'}), (t:EffectorType {uid: 't0'})
            CREATE (e:Entry {uid: $uid, active: true})-[:HAS_FACILITY]->(f)
            CREATE (e)-[:HAS_EFFECTOR]->(:Effector {uid: 'eff-' + $uid})
            CREATE (e)-[:HAS_EFFECTOR_TYPE]->(t)
            """,
            {"uid": uid},
        )
    await neo4j_graph.cypher_query(
        """
        MATCH (sm:Directory {name: 'sm'}), (open:Directory {name: 'open'}), (e:Entry) WHERE e.uid <> 'open-porteur'
        CREATE (sm)-[:HAS_ENTRY]->(e)
        WITH open
        MATCH (p:Entry {uid: 'open-porteur'}) CREATE (open)-[:HAS_ENTRY]->(p)
        """
    )
    await neo4j_graph.cypher_query(
        """
        MATCH (need:Entry {uid: 'need'}), (sub:Entry {uid: 'subneed'}), (cond:Entry {uid: 'condition'}),
              (sit:Entry {uid: 'situation'}), (typed:Entry {uid: 'type'}), (other:Entry {uid: 'other-need'}),
              (mental:Need {uid: 'n-sm'}), (psy:Need {uid: 'n-psy'}), (vivre:Need {uid: 'n-viv'}),
              (disorder:Condition {uid: 'c-di'}), (crisis:Situation {uid: 's-cr'}), (t2:EffectorType {uid: 't2'})
        CREATE (need)-[:MANAGES]->(mental), (sub)-[:MANAGES]->(psy), (cond)-[:MANAGES]->(disorder),
               (sit)-[:MANAGES]->(crisis), (other)-[:MANAGES]->(vivre)
        WITH typed, t2
        MATCH (typed)-[old:HAS_EFFECTOR_TYPE]->(:EffectorType) DELETE old
        CREATE (typed)-[:HAS_EFFECTOR_TYPE]->(t2)
        """
    )
    return neo4j_graph


async def listed(adb, directory):
    query, params = get_entries_query(SimpleNamespace(name=directory))
    rows, columns = await adb.cypher_query(query, params)
    return sorted(row[columns.index("uid")] for row in rows)


async def test_the_entries_that_manage_the_need_or_what_impacts_it_are_listed(graph):
    assert await listed(graph, "sm") == ["condition", "need", "situation", "subneed", "type"]


async def test_a_porteur_that_manages_nothing_is_not_listed(graph):
    found = await listed(graph, "sm")
    assert "porteur" not in found


async def test_a_need_outside_the_tree_does_not_list_its_entries(graph):
    assert "other-need" not in await listed(graph, "sm")


async def test_a_directory_without_the_edge_lists_everything_it_has(graph):
    assert await listed(graph, "open") == ["open-porteur"]


async def test_the_unlisted_entry_is_still_there(graph):
    rows, _ = await graph.cypher_query(
        "MATCH (:Directory {name: 'sm'})-[:HAS_ENTRY]->(e:Entry {uid: 'porteur'}) RETURN count(e)"
    )
    assert rows[0][0] == 1
