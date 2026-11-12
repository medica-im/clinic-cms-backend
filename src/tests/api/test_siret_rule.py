"""An establishment's SIRET starts with the SIREN of the legal unit that runs it.

The SIRET is the SIREN followed by a 5-digit number, so it is checkable: when an
entry is run by a porteur that has a SIREN and sits at a facility that has a
SIRET, the two must agree. The rule only ever looks at the entry's own porteur
(RUN_BY), never up a chain, and says nothing while either number is missing: an
entry is allowed to be entered before its identifiers are known.

Three writes can break it, so each checks it first and refuses with nothing
written: attaching an entry to a porteur, giving a facility a SIRET, and giving
a porteur a SIREN.
"""
import pytest

from directory.run_by import RunByRefused, set_run_by
from directory.siret_rule import SiretMismatch, check_facility_siret, check_siren

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MGEN = "441921913"
LYON = "44192191300212"
RIVAL = "123456782"  # a valid SIREN that is not MGEN's


@pytest.fixture
async def graph(neo4j_graph):
    """MGEN (siren), a Lyon establishment (siret) at its own facility, and a rival porteur."""
    await neo4j_graph.cypher_query(
        """
        CREATE (:Entry {uid: 'mgen', siren: $mgen})
        CREATE (:Entry {uid: 'rival', siren: $rival})
        CREATE (:Entry {uid: 'bare'})
        CREATE (l:Entry {uid: 'lyon'})-[:HAS_FACILITY]->(:Facility {uid: 'f-lyon', siret: $lyon})
        CREATE (n:Entry {uid: 'nowhere'})-[:HAS_FACILITY]->(:Facility {uid: 'f-none'})
        """,
        {"mgen": MGEN, "rival": RIVAL, "lyon": LYON},
    )
    return neo4j_graph


async def edges(adb):
    rows, _ = await adb.cypher_query("MATCH (e:Entry)-[:RUN_BY]->(p:Entry) RETURN e.uid, p.uid ORDER BY e.uid")
    return rows


async def test_an_establishment_may_be_run_by_the_legal_unit_its_siret_belongs_to(graph):
    await set_run_by("lyon", "mgen")
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_it_may_not_be_run_by_another_legal_unit_and_nothing_is_written(graph):
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("lyon", "rival")
    assert refused.value.code == "siret_mismatch"
    assert await edges(graph) == []


async def test_a_refused_porteur_leaves_the_current_one(graph):
    await set_run_by("lyon", "mgen")
    with pytest.raises(RunByRefused):
        await set_run_by("lyon", "rival")
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_nothing_is_checked_while_a_number_is_missing(graph):
    await set_run_by("lyon", "bare")          # the porteur has no SIREN yet
    await set_run_by("nowhere", "rival")      # the facility has no SIRET yet
    assert await edges(graph) == [["lyon", "bare"], ["nowhere", "rival"]]


async def test_a_siret_the_porteur_agrees_with_may_be_given_to_the_facility(graph):
    await set_run_by("lyon", "mgen")
    await check_facility_siret("f-lyon", "44192191300014")  # MGEN's head office number, same SIREN


async def test_a_siret_of_another_legal_unit_is_refused_for_a_facility_whose_entry_it_runs(graph):
    await set_run_by("lyon", "mgen")
    with pytest.raises(SiretMismatch):
        await check_facility_siret("f-lyon", RIVAL + "00011")


async def test_a_facility_whose_entries_have_no_porteur_takes_any_siret(graph):
    await check_facility_siret("f-lyon", RIVAL + "00011")


async def test_removing_a_siret_is_always_fine(graph):
    await set_run_by("lyon", "mgen")
    await check_facility_siret("f-lyon", None)


async def test_a_siren_that_disagrees_with_a_service_siret_is_refused(graph):
    await set_run_by("lyon", "mgen")
    with pytest.raises(SiretMismatch):
        await check_siren("mgen", RIVAL)


async def test_a_siren_that_agrees_or_is_removed_is_fine(graph):
    await set_run_by("lyon", "mgen")
    await check_siren("mgen", MGEN)
    await check_siren("mgen", None)


async def test_a_siren_for_a_porteur_with_no_service_is_not_checked(graph):
    await check_siren("rival", MGEN)


async def test_only_the_entrys_own_porteur_is_looked_at_not_a_chain(graph):
    await neo4j_chain(graph)
    await check_siren("rival", RIVAL)  # 'lyon' runs 'mgen' runs 'rival': rival is not lyon's porteur


async def neo4j_chain(adb):
    await adb.cypher_query(
        "MATCH (m:Entry {uid: 'mgen'}), (r:Entry {uid: 'rival'}), (l:Entry {uid: 'lyon'}) "
        "CREATE (l)-[:RUN_BY]->(m), (m)-[:RUN_BY]->(r)"
    )
