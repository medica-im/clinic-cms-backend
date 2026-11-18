"""MANAGES from an Entry: what this one entry handles.

A CMP handles several conditions, one CCAS service is mental health and another is
not, so what an entry handles is stored on the entry, not only on its type (the
type-level MANAGES stays and is never touched here). Targets are Conditions,
Situations and Needs, matched by slug because the same node has a different uid on
each Neo4j server. Written through the official driver and checked before anything
is changed: a refusal leaves the entry's edges exactly as they were.
"""
import pytest

from directory.manages import ManagesRefused, get_managed, get_manages, set_manages, unknown_slugs

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (:Entry {uid: 'cmp', active: true, access: 'anonymous'})
        CREATE (:Entry {uid: 'other', active: true, access: 'anonymous'})
        CREATE (:Condition {uid: 'c1', slug: 'addictions'})
        CREATE (:Condition {uid: 'c2', slug: 'troubles-anxieux'})
        CREATE (:Situation {uid: 's1', slug: 'crise-suicidaire'})
        CREATE (:Need {uid: 'n1', slug: 'sante-mentale'})
        CREATE (:EffectorType {uid: 'et', name_fr: 'CMP'})
        CREATE (:Tag {uid: 't1', slug: 'not-a-concern'})
        """
    )
    return neo4j_graph


async def edges(adb, entry="cmp"):
    rows, _ = await adb.cypher_query(
        "MATCH (:Entry {uid: $entry})-[:MANAGES]->(t) RETURN t.slug ORDER BY t.slug", {"entry": entry}
    )
    return [row[0] for row in rows]


async def test_an_entry_manages_conditions_situations_and_needs(graph):
    await set_manages("cmp", ["troubles-anxieux", "crise-suicidaire", "sante-mentale"])
    assert await edges(graph) == ["crise-suicidaire", "sante-mentale", "troubles-anxieux"]


async def test_the_new_list_replaces_the_old_one(graph):
    await set_manages("cmp", ["addictions", "troubles-anxieux"])
    await set_manages("cmp", ["addictions"])
    assert await edges(graph) == ["addictions"]


async def test_an_empty_list_detaches_everything(graph):
    await set_manages("cmp", ["addictions"])
    await set_manages("cmp", [])
    assert await edges(graph) == []


async def test_a_repeated_slug_is_one_edge(graph):
    await set_manages("cmp", ["addictions", "addictions"])
    rows, _ = await graph.cypher_query("MATCH (:Entry {uid: 'cmp'})-[r:MANAGES]->() RETURN count(r)")
    assert rows[0][0] == 1


async def test_another_entry_is_untouched(graph):
    await set_manages("other", ["addictions"])
    await set_manages("cmp", ["troubles-anxieux"])
    assert await edges(graph, "other") == ["addictions"]


async def test_the_type_level_edge_stays(graph):
    await graph.cypher_query("MATCH (et:EffectorType), (n:Need) CREATE (et)-[:MANAGES]->(n)")
    await set_manages("cmp", [])
    rows, _ = await graph.cypher_query("MATCH (:EffectorType)-[r:MANAGES]->(:Need) RETURN count(r)")
    assert rows[0][0] == 1


@pytest.mark.parametrize(
    "entry, slugs, code",
    [
        ("nope", ["addictions"], "unknown_entry"),
        ("cmp", ["nope"], "unknown_target"),
        ("cmp", ["addictions", "nope"], "unknown_target"),
        ("cmp", ["not-a-concern"], "unknown_target"),
    ],
)
async def test_a_refusal_has_a_code_and_changes_nothing(graph, entry, slugs, code):
    await set_manages("cmp", ["troubles-anxieux"])
    with pytest.raises(ManagesRefused) as refused:
        await set_manages(entry, slugs)
    assert refused.value.code == code
    assert await edges(graph) == ["troubles-anxieux"]


async def test_the_unknown_slug_is_named(graph):
    with pytest.raises(ManagesRefused) as refused:
        await set_manages("cmp", ["addictions", "nope"])
    assert refused.value.slugs == ["nope"]


async def test_unknown_slugs_can_be_checked_before_an_entry_exists(graph):
    assert await unknown_slugs(["addictions", "nope", "not-a-concern"]) == ["nope", "not-a-concern"]
    assert await unknown_slugs([]) == []


async def test_get_manages_returns_the_slugs_sorted(graph):
    await set_manages("cmp", ["troubles-anxieux", "addictions"])
    assert await get_manages("cmp") == ["addictions", "troubles-anxieux"]
    assert await get_manages("other") == []


async def test_what_it_manages_reads_by_name_conditions_then_situations_then_the_need(graph):
    """What the entry page shows as étiquettes: a reader sees names, not slugs."""
    await graph.cypher_query(
        "MATCH (a {uid: 'c1'}), (b {uid: 'c2'}), (s {uid: 's1'}), (n {uid: 'n1'}) "
        "SET a.name_fr = 'Addictions', b.name_fr = 'Troubles anxieux', s.name_fr = 'Crise suicidaire', "
        "n.name_fr = 'santé mentale'"
    )
    await set_manages("cmp", ["sante-mentale", "crise-suicidaire", "troubles-anxieux", "addictions"])
    assert await get_managed("cmp") == [
        {"slug": "addictions", "name": "Addictions", "kind": "condition"},
        {"slug": "troubles-anxieux", "name": "Troubles anxieux", "kind": "condition"},
        {"slug": "crise-suicidaire", "name": "Crise suicidaire", "kind": "situation"},
        {"slug": "sante-mentale", "name": "santé mentale", "kind": "need"},
    ]
    assert await get_managed("other") == []
