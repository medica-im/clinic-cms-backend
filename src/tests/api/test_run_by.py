"""RUN_BY: who runs an entry.

An entry may be run by another entry, its porteur: a service by the organization
behind it, an establishment (MGEN's hospital de jour in Lyon) by the legal unit
that owns it. (service)-[:RUN_BY]->(porteur), at most one per entry, chains
allowed (a hospital runs a pole runs a CMP), never a loop. The edge is written
through the official driver: replaced, never added to, because nothing in Neo4j
stops a second one and the entry would then appear twice in the API.

What is pinned here is the graph: one edge after any sequence of writes, a
refusal that leaves what was there untouched, and a tree that stays a tree.
"""
import pytest

from api.utils import ALLOWED_ACCESS
from directory.run_by import RunByRefused, name_order, related_entries, services_of, set_run_by, visible_around

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        "UNWIND ['mgen', 'lyon', 'pole', 'cmp', 'other'] AS uid CREATE (:Entry {uid: uid})"
    )
    return neo4j_graph


async def edges(adb, entry=None):
    rows, _ = await adb.cypher_query(
        "MATCH (e:Entry)-[:RUN_BY]->(p:Entry) WHERE $entry IS NULL OR e.uid = $entry "
        "RETURN e.uid, p.uid ORDER BY e.uid, p.uid",
        {"entry": entry},
    )
    return rows


async def test_an_entry_is_run_by_its_porteur(graph):
    await set_run_by("lyon", "mgen")
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_running_it_again_leaves_one_edge(graph):
    await set_run_by("lyon", "mgen")
    await set_run_by("lyon", "mgen")
    assert await edges(graph, "lyon") == [["lyon", "mgen"]]


async def test_another_porteur_replaces_the_first_instead_of_adding_one(graph):
    await set_run_by("lyon", "mgen")
    await set_run_by("lyon", "other")
    assert await edges(graph, "lyon") == [["lyon", "other"]]


async def test_nobody_detaches_the_entry(graph):
    await set_run_by("lyon", "mgen")
    await set_run_by("lyon", None)
    assert await edges(graph) == []


async def test_detaching_an_entry_that_has_no_porteur_is_fine(graph):
    await set_run_by("lyon", None)
    assert await edges(graph) == []


async def test_many_services_may_have_the_same_porteur(graph):
    await set_run_by("lyon", "mgen")
    await set_run_by("other", "mgen")
    assert await edges(graph) == [["lyon", "mgen"], ["other", "mgen"]]


async def test_a_chain_of_porteurs_is_allowed(graph):
    await set_run_by("cmp", "pole")
    await set_run_by("pole", "mgen")
    assert await edges(graph) == [["cmp", "pole"], ["pole", "mgen"]]


async def test_an_unknown_entry_is_refused_and_nothing_is_written(graph):
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("nope", "mgen")
    assert refused.value.code == "unknown_entry"
    assert await edges(graph) == []


async def test_an_unknown_porteur_is_refused_and_the_current_one_is_kept(graph):
    await set_run_by("lyon", "mgen")
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("lyon", "nope")
    assert refused.value.code == "unknown_porteur"
    assert await edges(graph, "lyon") == [["lyon", "mgen"]]


async def test_an_entry_cannot_run_itself(graph):
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("mgen", "mgen")
    assert refused.value.code == "cycle"
    assert await edges(graph) == []


async def test_a_loop_through_one_entry_is_refused(graph):
    await set_run_by("lyon", "mgen")
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("mgen", "lyon")
    assert refused.value.code == "cycle"
    assert await edges(graph) == [["lyon", "mgen"]]


async def test_a_loop_through_a_longer_chain_is_refused_and_leaves_it_as_it_was(graph):
    await set_run_by("cmp", "pole")
    await set_run_by("pole", "mgen")
    with pytest.raises(RunByRefused) as refused:
        await set_run_by("mgen", "cmp")
    assert refused.value.code == "cycle"
    assert await edges(graph) == [["cmp", "pole"], ["pole", "mgen"]]


async def test_services_of_a_porteur_are_the_entries_it_runs_directly(graph):
    await set_run_by("lyon", "mgen")
    await set_run_by("other", "mgen")
    await set_run_by("cmp", "pole")
    assert sorted(await services_of("mgen")) == ["lyon", "other"]
    assert await services_of("pole") == ["cmp"]
    assert await services_of("lyon") == []


# --- What a page shows of the entries around it --------------------------------------


@pytest.fixture
async def named(neo4j_graph):
    """MGEN and its establishment, each with a person (Effector) and a type."""
    await neo4j_graph.cypher_query(
        """
        CREATE (m:Entry {uid: 'mgen', slug: 'mgen-action-sanitaire-et-sociale', active: true, access: 'anonymous'})
        CREATE (m)-[:HAS_EFFECTOR]->(:Effector {uid: 'e-mgen', name_fr: 'MGEN Action sanitaire et sociale', label_fr: 'MGEN'})
        CREATE (m)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't-mut', label_fr: 'organisme mutualiste', name_fr: 'organisme mutualiste'})
        CREATE (l:Entry {uid: 'lyon', slug: 'etablissement-de-sante-mentale-lyon', active: true, access: 'anonymous'})
        CREATE (l)-[:HAS_EFFECTOR]->(:Effector {uid: 'e-lyon', name_fr: 'Établissement de santé mentale de Lyon', label_fr: 'ESM Lyon'})
        CREATE (l)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't-hdj', label_fr: 'hôpital de jour', name_fr: 'hôpital de jour'})
        CREATE (z:Entry {uid: 'zeta', slug: 'zeta', active: true, access: 'anonymous'})
        CREATE (z)-[:HAS_EFFECTOR]->(:Effector {uid: 'e-zeta', name_fr: 'Annexe Zeta', label_fr: 'Zeta'})
        CREATE (z)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: 't-hdj2', label_fr: 'hôpital de jour', name_fr: 'hôpital de jour'})
        """
    )
    await set_run_by("lyon", "mgen")
    await set_run_by("zeta", "mgen")
    return neo4j_graph


async def test_an_entry_names_its_porteur_with_what_a_page_needs_to_link_to_it(named):
    around = await related_entries("lyon", "fr")
    assert around["run_by"] == {
        "uid": "mgen",
        "slug": "mgen-action-sanitaire-et-sociale",
        "name": "MGEN Action sanitaire et sociale",
        "label": "MGEN",
        "effector_type": "organisme mutualiste",
        "access": "anonymous",
        "siren": None,
    }
    assert around["services"] == []


async def test_a_porteur_lists_the_entries_it_runs_by_name(named):
    around = await related_entries("mgen", "fr")
    assert around["run_by"] is None
    assert [s["name"] for s in around["services"]] == ["Annexe Zeta", "Établissement de santé mentale de Lyon"]
    assert around["services"][1]["effector_type"] == "hôpital de jour"


async def test_an_inactive_entry_is_not_shown_around_the_others(named):
    await named.cypher_query("MATCH (e:Entry {uid: 'zeta'}) SET e.active = false")
    assert [s["uid"] for s in (await related_entries("mgen", "fr"))["services"]] == ["lyon"]
    await named.cypher_query("MATCH (e:Entry {uid: 'mgen'}) SET e.active = false")
    assert (await related_entries("lyon", "fr"))["run_by"] is None


async def test_the_name_falls_back_to_english_when_the_language_has_none(named):
    await named.cypher_query("MATCH (f:Effector {uid: 'e-lyon'}) SET f.name_fr = null, f.name_en = 'Lyon mental health centre'")
    around = await related_entries("mgen", "fr")
    assert "Lyon mental health centre" in [s["name"] for s in around["services"]]


async def test_an_entry_with_nothing_around_it_has_neither(graph):
    assert await related_entries("lyon", "fr") == {"run_by": None, "services": []}


def test_a_viewer_sees_only_the_entries_their_role_may_see():
    around = {
        "run_by": {"uid": "p", "access": "staff"},
        "services": [{"uid": "a", "access": "anonymous"}, {"uid": "b", "access": "staff"}, {"uid": "c", "access": "administrator"}],
    }
    assert visible_around(around, ALLOWED_ACCESS.get("anonymous")) == {"run_by": None, "services": [{"uid": "a", "access": "anonymous"}]}
    assert [s["uid"] for s in visible_around(around, ALLOWED_ACCESS.get("staff"))["services"]] == ["a", "b"]
    assert visible_around(around, ALLOWED_ACCESS.get("staff"))["run_by"]["uid"] == "p"
    assert [s["uid"] for s in visible_around(around, ALLOWED_ACCESS.get("administrator"))["services"]] == ["a", "b", "c"]


def test_a_superuser_sees_everything():
    around = {"run_by": {"uid": "p", "access": "administrator"}, "services": [{"uid": "c", "access": "administrator"}]}
    assert visible_around(around, ALLOWED_ACCESS.get("superuser")) == around


def test_names_are_ordered_as_a_french_reader_expects():
    names = ["Zeta", "Établissement", "annexe", "écho", "Eau", None]
    assert sorted(names, key=name_order) == [None, "annexe", "Eau", "écho", "Établissement", "Zeta"]
