"""The SIRET of a facility: who may set it, and when it is written.

A SIRET says which legal establishment a place is, so, like an entry's run_by and
SIREN, it is an administrator's or a superuser's to set. Two things matter for
the edit forms that already exist: a PUT that does not mention the SIRET leaves
it alone (those forms do not know it), and sending the SIRET the facility already
has changes nothing, so no role is asked for it. And it must agree with the SIREN
of the porteur of every entry at the facility.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.serializers.facility import check_siret_write, set_siret_if_sent
from api.types.facility import FacilityPut

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LYON = "44192191300212"
HEAD_OFFICE = "44192191300014"
RIVAL = "12345678200002"  # a valid SIRET of a legal unit that is not MGEN

BODY = {
    "name": "n", "label": "l", "slug": "s", "building": None, "street": None, "geographical_complement": None,
    "zip": "69003", "ban_id": None, "ban_banId": None,
}


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (m:Entry {uid: 'mgen', siren: '441921913'})
        CREATE (l:Entry {uid: 'lyon'})-[:HAS_FACILITY]->(:Facility {uid: 'f-lyon', siret: $lyon})
        CREATE (l)-[:RUN_BY]->(m)
        CREATE (:Facility {uid: 'f-new'})
        """,
        {"lyon": LYON},
    )
    return neo4j_graph


def put(**extra):
    return FacilityPut(**BODY, **extra)


@pytest.mark.parametrize("role", ["administrator", "superuser"])
async def test_an_administrator_or_a_superuser_sets_a_siret(graph, role):
    await check_siret_write("f-new", put(siret=LYON), role)


@pytest.mark.parametrize("role", ["staff", "registered", None])
async def test_nobody_else_may_set_one(graph, role):
    with pytest.raises(HTTPException) as refused:
        await check_siret_write("f-new", put(siret=LYON), role)
    assert refused.value.status_code == 403


async def test_a_put_that_does_not_mention_the_siret_asks_for_no_role(graph):
    await check_siret_write("f-lyon", put(), "staff")


async def test_sending_the_siret_the_facility_already_has_asks_for_no_role(graph):
    await check_siret_write("f-lyon", put(siret=LYON), "staff")


async def test_removing_a_siret_is_a_change_and_asks_for_the_role(graph):
    with pytest.raises(HTTPException) as refused:
        await check_siret_write("f-lyon", put(siret=None), "staff")
    assert refused.value.status_code == 403
    await check_siret_write("f-lyon", put(siret=None), "administrator")


async def test_a_siret_of_the_same_legal_unit_is_accepted(graph):
    await check_siret_write("f-lyon", put(siret=HEAD_OFFICE), "administrator")


async def test_a_siret_of_another_legal_unit_is_a_409(graph):
    with pytest.raises(HTTPException) as refused:
        await check_siret_write("f-lyon", put(siret=RIVAL), "superuser")
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "siret_mismatch"}


async def test_a_new_facility_has_no_current_siret_and_no_entry_to_disagree_with(graph):
    await check_siret_write(None, put(siret=LYON), "administrator")
    with pytest.raises(HTTPException):
        await check_siret_write(None, put(siret=LYON), "staff")


def test_the_siret_is_written_only_when_it_was_sent():
    node = SimpleNamespace(siret=LYON)
    set_siret_if_sent(node, put())
    assert node.siret == LYON
    set_siret_if_sent(node, put(siret=HEAD_OFFICE))
    assert node.siret == HEAD_OFFICE
    set_siret_if_sent(node, put(siret=None))
    assert node.siret is None
