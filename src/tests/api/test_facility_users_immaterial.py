"""Who answers for a facility, when a help line sits on its porteur's address.

A service with no premises of its own uses its porteur's facility (the 3114 at Le
Vinatier). Creating that help line must not let its creator edit Le Vinatier's
facility: an entry of an immaterial type is not located there in any sense that
gives rights over the place. Owners and creators of the facility itself, and of
the material entries at it, still answer for it (CLAUDE.md, authorization rule 2).
Real Neo4j: the rule lives in the Cypher.
"""
import pytest

from api.routers.facilities import get_facility_users

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (f:Facility {uid: 'f1'})
        CREATE (fu:User {uid: 'facility-creator'}), (ou:User {uid: 'cmp-owner'}), (cu:User {uid: 'cmp-creator'}),
               (lo:User {uid: 'line-owner'}), (lc:User {uid: 'line-creator'}), (so:User {uid: 'subtype-owner'})
        CREATE (f)-[:CREATED_BY]->(fu)
        CREATE (material:EffectorType {uid: 't-cmp'}), (line:EffectorType {uid: 't-line', immaterial: true}),
               (sub:EffectorType {uid: 't-sub'})
        CREATE (sub)-[:IS_A]->(line)
        CREATE (cmp:Entry {uid: 'cmp'})-[:HAS_FACILITY]->(f), (cmp)-[:HAS_EFFECTOR_TYPE]->(material)
        CREATE (cmp)-[:OWNED_BY]->(ou), (cmp)-[:CREATED_BY]->(cu)
        CREATE (help:Entry {uid: 'help-line'})-[:HAS_FACILITY]->(f), (help)-[:HAS_EFFECTOR_TYPE]->(line)
        CREATE (help)-[:OWNED_BY]->(lo), (help)-[:CREATED_BY]->(lc)
        CREATE (sublet:Entry {uid: 'sub-line'})-[:HAS_FACILITY]->(f), (sublet)-[:HAS_EFFECTOR_TYPE]->(sub)
        CREATE (sublet)-[:OWNED_BY]->(so)
        """
    )
    return neo4j_graph


async def answering(uid="f1"):
    return sorted(user.uid for user in await get_facility_users(uid))


async def test_the_facility_and_its_material_entries_answer_for_it(graph):
    found = await answering()
    assert {"facility-creator", "cmp-owner", "cmp-creator"} <= set(found)


async def test_an_entry_of_an_immaterial_type_gives_its_people_no_rights(graph):
    found = await answering()
    assert "line-owner" not in found
    assert "line-creator" not in found


async def test_nor_does_an_entry_of_a_subtype_of_an_immaterial_type(graph):
    assert "subtype-owner" not in await answering()


async def test_a_type_not_marked_immaterial_changes_nothing(graph):
    await graph.cypher_query("MATCH (t:EffectorType {uid: 't-line'}) REMOVE t.immaterial")
    found = await answering()
    assert {"line-owner", "line-creator", "subtype-owner"} <= set(found)
