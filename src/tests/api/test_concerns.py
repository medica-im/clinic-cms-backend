"""The conditions and situations a directory offers, with the entries each one selects.

Picking X lists the entries that manage X or a descendant of X, never an ancestor:
in a mental health directory everything relates to mental health, so walking up
would return everything for everything. An entry manages something through its
own MANAGES or its type's. Only the directory's own, active entries count, and a
node nobody manages (an empty chapter) is not offered. "Voir aussi" follows
MAY_LEAD_TO to the situations or conditions a condition can lead to, when those are
offered too. Real Neo4j: the semantics live in the Cypher.
"""
import pytest

from directory.concerns import concerns_of_directory

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (d:Directory {name: 'sm'}), (o:Directory {name: 'other'})
        CREATE (addictions:Condition:Chapter {uid: 'c-add', slug: 'addictions', name_fr: 'Troubles addictifs', label_fr: 'Addictions', kind: 'chapter', synonyms_fr: ['dépendance']})
        CREATE (alcool:Condition {uid: 'c-alc', slug: 'addiction-alcool', name_fr: 'Alcool', kind: 'condition'})
        CREATE (alcool)-[:PART_OF]->(addictions)
        CREATE (anxieux:Condition:Chapter {uid: 'c-anx', slug: 'troubles-anxieux', name_fr: 'Troubles anxieux', kind: 'chapter'})
        CREATE (empty:Condition:Chapter {uid: 'c-emp', slug: 'vide', name_fr: 'Chapitre vide', kind: 'chapter'})
        CREATE (unused:Condition {uid: 'c-unu', slug: 'inutilise', name_fr: 'Inutilisé'})
        CREATE (unused)-[:PART_OF]->(empty)
        CREATE (depression:Condition {uid: 'c-dep', slug: 'depression', name_fr: 'Dépression', kind: 'condition'})
        CREATE (crise:Situation {uid: 's-cri', slug: 'crise-suicidaire', name_fr: 'Crise suicidaire'})
        CREATE (depression)-[:MAY_LEAD_TO]->(crise)
        CREATE (depression)-[:MAY_LEAD_TO]->(:Situation {uid: 's-off', slug: 'nobody-manages', name_fr: 'Personne'})

        CREATE (e1:Entry {uid: 'e-own', active: true}), (e2:Entry {uid: 'e-type', active: true}),
               (e3:Entry {uid: 'e-off', active: false}), (e4:Entry {uid: 'e-other', active: true}),
               (e5:Entry {uid: 'e-3114', active: true}), (e6:Entry {uid: 'e-dep', active: true}),
               (e7:Entry {uid: 'e-sub', active: true})
        CREATE (d)-[:HAS_ENTRY]->(e1), (d)-[:HAS_ENTRY]->(e2), (d)-[:HAS_ENTRY]->(e3),
               (d)-[:HAS_ENTRY]->(e5), (d)-[:HAS_ENTRY]->(e6), (d)-[:HAS_ENTRY]->(e7),
               (o)-[:HAS_ENTRY]->(e4)
        CREATE (e1)-[:MANAGES]->(alcool)
        CREATE (e3)-[:MANAGES]->(alcool)
        CREATE (e4)-[:MANAGES]->(alcool)
        CREATE (e5)-[:MANAGES]->(crise)
        CREATE (e6)-[:MANAGES]->(depression)
        CREATE (csapa:EffectorType {uid: 't-csapa'}), (sub:EffectorType {uid: 't-sub'})
        CREATE (sub)-[:IS_A]->(csapa)
        CREATE (csapa)-[:MANAGES]->(anxieux)
        CREATE (e2)-[:HAS_EFFECTOR_TYPE]->(csapa)
        CREATE (e7)-[:HAS_EFFECTOR_TYPE]->(sub)
        """
    )
    return neo4j_graph


async def offered(directory="sm"):
    return {c["slug"]: c for c in await concerns_of_directory(directory)}


async def test_picking_a_node_selects_its_own_entries_and_its_descendants(graph):
    found = await offered()
    assert found["addiction-alcool"]["entries"] == ["e-own"]
    assert found["addictions"]["entries"] == ["e-own"]


async def test_an_entry_managing_a_chapter_is_not_selected_by_a_condition_under_it(graph):
    await graph.cypher_query("MATCH (e:Entry {uid: 'e-dep'}), (c:Condition {slug: 'addictions'}) CREATE (e)-[:MANAGES]->(c)")
    found = await offered()
    assert "e-dep" in found["addictions"]["entries"]
    assert "e-dep" not in found["addiction-alcool"]["entries"]


async def test_a_type_level_manages_selects_the_entries_of_the_type_and_its_subtypes(graph):
    found = await offered()
    assert sorted(found["troubles-anxieux"]["entries"]) == ["e-sub", "e-type"]


async def test_inactive_entries_and_other_directories_never_count(graph):
    found = await offered()
    assert "e-off" not in found["addiction-alcool"]["entries"]
    assert "e-other" not in found["addiction-alcool"]["entries"]
    assert (await offered("other"))["addiction-alcool"]["entries"] == ["e-other"]


async def test_a_node_nobody_manages_is_not_offered(graph):
    found = await offered()
    assert "vide" not in found
    assert "inutilise" not in found


async def test_the_tree_is_given_by_parent_uid(graph):
    found = await offered()
    assert found["addiction-alcool"]["parent"] == "c-add"
    assert found["addictions"]["parent"] is None


async def test_kind_name_and_synonyms_are_what_the_selector_shows_and_searches(graph):
    found = await offered()
    assert found["addictions"]["kind"] == "chapter"
    assert found["addictions"]["name"] == "Addictions"
    assert found["addictions"]["synonyms"] == ["dépendance"]
    assert found["addiction-alcool"]["kind"] == "condition"
    assert found["addiction-alcool"]["name"] == "Alcool"
    assert found["crise-suicidaire"]["kind"] == "situation"


async def test_voir_aussi_lists_the_offered_situations_a_condition_can_lead_to(graph):
    found = await offered()
    assert found["depression"]["see_also"] == ["s-cri"]
    assert found["crise-suicidaire"]["see_also"] == []


async def test_voir_aussi_also_follows_a_condition_to_a_condition(graph):
    """Bipolar disorder may lead to suicidal ideation, which ICD-11 codes as a
    condition (MB26.A), not a situation: its entries belong in "voir aussi" too."""
    await graph.cypher_query(
        """
        MATCH (d:Directory {name: 'sm'})
        CREATE (bipolaire:Condition {uid: 'c-bip', slug: 'bipolaire', name_fr: 'Troubles bipolaires', kind: 'condition'})
        CREATE (idees:Condition {uid: 'c-ide', slug: 'idees-suicidaires', name_fr: 'Idées suicidaires', kind: 'condition'})
        CREATE (bipolaire)-[:MAY_LEAD_TO]->(idees)
        CREATE (d)-[:HAS_ENTRY]->(:Entry {uid: 'e-bip', active: true})-[:MANAGES]->(bipolaire)
        CREATE (d)-[:HAS_ENTRY]->(:Entry {uid: 'e-ide', active: true})-[:MANAGES]->(idees)
        """
    )
    found = await offered()
    assert found["bipolaire"]["see_also"] == ["c-ide"]


async def test_an_entry_with_two_paths_to_a_node_is_listed_once(graph):
    await graph.cypher_query("MATCH (e:Entry {uid: 'e-own'}), (c:Condition {slug: 'addictions'}) CREATE (e)-[:MANAGES]->(c)")
    found = await offered()
    assert found["addictions"]["entries"] == ["e-own"]


async def test_an_unknown_directory_offers_nothing(graph):
    assert await concerns_of_directory("nope") == []
