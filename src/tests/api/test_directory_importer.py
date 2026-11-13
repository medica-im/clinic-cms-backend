"""Importing a directory's entries from a spec: porteurs, then the entries they run.

The spec names everything the way people do (a type by its slug, a commune by its
name, a department by its code, a porteur by a key, an entry already there by its
slug), because uids differ on every backend. Nothing is written until every name
resolves, and every write is found-or-created by a natural key, so a rerun after
a failure finishes the job and a rerun after success changes nothing.
Real Neo4j: the natural keys live in the Cypher.
"""
import copy

import pytest

from directory.importer import import_spec, preflight

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BRON = {"label": "95 Boulevard Pinel 69500 Bron", "street": "95 Boulevard Pinel", "zip": "69500", "city": "Bron",
        "citycode": "69029", "latitude": 45.73, "longitude": 4.89, "ban_id": "69029_x_00095", "ban_banId": None}

SPEC = {
    "directory": "sm",
    "porteurs": [
        {"key": "vinatier", "name": "Centre hospitalier Le Vinatier", "label": "Le Vinatier", "type": "hopitaux",
         "siren": "266900083", "manages": [],
         "facility": {"name": "Centre hospitalier Le Vinatier", "address": BRON, "building": None}},
    ],
    "entries": [
        {"key": "row-5", "row": 5, "name": "3114 (Numéro national de prévention du suicide)", "label": "3114",
         "type": "ligne-ecoute", "existing": None, "siren": None, "facility": {"porteur": "vinatier"},
         "run_by": "vinatier", "manages": ["idees-suicidaires", "crise-suicidaire"],
         "coverage": [{"department": "69"}, {"country": "FR"}],
         "facets": {"age_min": None, "age_max": None, "care_levels": ["emergency"], "who_can_contact": "anyone",
                    "access_modes": ["phone"], "audiences": None, "free": None, "anonymous_care": None},
         "phones": ["3114"], "emails": [], "websites": [], "description": None},
        {"key": "row-9", "row": 9, "name": "POP", "label": None, "type": "centre-ressource", "existing": None,
         "siren": None, "facility": {"name": "Centre hospitalier Le Vinatier", "address": BRON, "building": None},
         "run_by": "vinatier", "manages": ["sante-mentale"], "coverage": [], "facets": {}, "phones": [], "emails": [],
         "websites": [], "description": None},
        {"key": "row-67", "row": 67, "name": "CMP Les Quadrilles", "label": None, "type": "centre-medico-psychologique",
         "existing": "cmp-old", "siren": None, "facility": None, "run_by": "vinatier", "manages": ["sante-mentale"],
         "coverage": [], "facets": {}, "phones": [], "emails": [], "websites": [], "description": None},
    ],
}


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (:Directory {name: 'sm'})-[:HAS_ENTRY]->(old:Entry {uid: 'e-old', slug: 'cmp-old', active: true})
        CREATE (old)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-old', name_fr: 'CMP Les Quadrilles'})
        CREATE (old)-[:HAS_FACILITY]->(:Facility {uid: 'f-old', street: '19 rue Jacqueline Auriol', zip: '69008'})
        CREATE (old)-[:HAS_EFFECTOR_TYPE]->(cmp:EffectorType {uid: 't-cmp', slug_fr: 'centre-medico-psychologique', name_fr: 'centre médico-psychologique'})
        CREATE (:EffectorType {uid: 't-hop', slug_fr: 'hopitaux', name_fr: 'hôpital'})
        CREATE (:EffectorType {uid: 't-line', slug_fr: 'ligne-ecoute', name_fr: "ligne d'écoute"})
        CREATE (:EffectorType {uid: 't-res', slug_fr: 'centre-ressource', name_fr: 'centre ressource'})
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'c-bron', name_fr: 'Bron', slug_fr: 'bron'})
        CREATE (:DepartmentOfFrance {uid: 'd-69', code: '69', name: 'Rhône'})
        CREATE (:Country {uid: 'fr', code: 'FR', name: 'France'})
        CREATE (:Condition {uid: 'c-ide', slug: 'idees-suicidaires', name_fr: 'Idées suicidaires'})
        CREATE (:Situation {uid: 's-cri', slug: 'crise-suicidaire', name_fr: 'Crise suicidaire'})
        CREATE (:Need {uid: 'n-sm', slug: 'sante-mentale', name_fr: 'santé mentale'})
        """
    )
    return neo4j_graph


async def one(graph, query, **params):
    rows, _ = await graph.cypher_query(query, params)
    return rows


async def entry_of(graph, name):
    rows = await one(graph, "MATCH (e:Entry)-[:HAS_EFFECTOR]->(:Effector {name_fr: $n}) RETURN e.uid", n=name)
    assert len(rows) == 1, rows
    return rows[0][0]


async def test_a_service_without_premises_answers_from_its_porteurs_facility(graph):
    await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    line = await entry_of(graph, "3114 (Numéro national de prévention du suicide)")
    rows = await one(
        graph,
        "MATCH (:Entry {uid: $e})-[:HAS_FACILITY]->(f)<-[:HAS_FACILITY]-(p:Entry)-[:HAS_EFFECTOR]->(:Effector {name_fr: 'Centre hospitalier Le Vinatier'}) "
        "MATCH (:Entry {uid: $e})-[:RUN_BY]->(p) MATCH (:Directory {name: 'sm'})-[:HAS_ENTRY]->(p) RETURN f.street, p.siren",
        e=line,
    )
    assert rows == [["95 Boulevard Pinel", "266900083"]]


async def test_what_it_manages_where_it_answers_and_its_facets_are_written(graph):
    await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    line = await entry_of(graph, "3114 (Numéro national de prévention du suicide)")
    manages = await one(graph, "MATCH (:Entry {uid: $e})-[:MANAGES]->(m) RETURN m.slug ORDER BY m.slug", e=line)
    covers = await one(graph, "MATCH (:Entry {uid: $e})-[:COVERS]->(t) RETURN t.uid ORDER BY t.uid", e=line)
    facets = await one(graph, "MATCH (e:Entry {uid: $e}) RETURN e.care_levels, e.who_can_contact, e.access_modes, e.age_min", e=line)
    assert [m[0] for m in manages] == ["crise-suicidaire", "idees-suicidaires"]
    assert [c[0] for c in covers] == ["d-69", "fr"]
    assert facets == [[["emergency"], "anyone", ["phone"], None]]


async def test_entries_at_the_same_street_share_one_facility(graph):
    await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    rows = await one(graph, "MATCH (f:Facility {street: '95 Boulevard Pinel', zip: '69500'}) RETURN f.name")
    assert rows == [["Centre hospitalier Le Vinatier"]]
    located = await one(graph, "MATCH (:Facility {street: '95 Boulevard Pinel'})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune) RETURN c.uid")
    assert located == [["c-bron"]]


async def test_an_entry_already_there_is_reused_by_its_slug_and_given_its_porteur(graph):
    await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    rows = await one(graph, "MATCH (e:Entry)-[:HAS_EFFECTOR]->(:Effector {name_fr: 'CMP Les Quadrilles'}) RETURN e.uid")
    assert rows == [["e-old"]]
    run_by = await one(graph, "MATCH (:Entry {uid: 'e-old'})-[:RUN_BY]->(p)-[:HAS_EFFECTOR]->(x) RETURN x.name_fr")
    assert run_by == [["Centre hospitalier Le Vinatier"]]


async def test_a_rerun_after_success_creates_nothing(graph):
    first = await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    before = await one(graph, "MATCH (n) RETURN count(n)")
    second = await import_spec(SPEC, creator_directory="santelyon3", contacts=False)
    assert sum(first.created.values()) > 0
    assert sum(second.created.values()) == 0
    assert await one(graph, "MATCH (n) RETURN count(n)") == before


async def test_only_imports_the_named_entries_and_the_porteurs_they_need(graph):
    await import_spec(SPEC, creator_directory="santelyon3", contacts=False, only={"row-9"})
    assert await one(graph, "MATCH (:Effector {name_fr: 'POP'}) RETURN count(*)") == [[1]]
    assert await one(graph, "MATCH (x:Effector) WHERE x.name_fr STARTS WITH '3114' RETURN count(x)") == [[0]]


async def test_nothing_is_written_until_every_name_resolves(graph):
    spec = copy.deepcopy(SPEC)
    spec["porteurs"][0]["type"] = "no-such-type"
    spec["porteurs"][0]["facility"]["address"] = {**BRON, "city": "Atlantis"}
    spec["entries"][0]["manages"].append("no-such-concern")
    spec["entries"][0]["coverage"].append({"department": "99"})
    spec["entries"][1]["run_by"] = "nobody"
    spec["entries"][2]["existing"] = "no-such-slug"
    problems = await preflight(spec)
    assert problems == [
        "vinatier: effector type 'no-such-type' is missing",
        "vinatier: commune 'Atlantis' is missing",
        "row-5: unknown manages 'no-such-concern'",
        "row-5: unknown department '99'",
        "row-9: unknown porteur 'nobody'",
        "row-67: no entry 'no-such-slug' in directory 'sm'",
    ]
    before = await one(graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(ValueError):
        await import_spec(spec, creator_directory="santelyon3", contacts=False)
    assert await one(graph, "MATCH (n) RETURN count(n)") == before


async def test_the_phones_go_on_the_entrys_contact(graph, transactional_db):
    from addressbook.models import Contact

    await import_spec(SPEC, creator_directory="santelyon3", contacts=True)
    line = await entry_of(graph, "3114 (Numéro national de prévention du suicide)")
    contact = await Contact.objects.aget(neomodel_uid=line)
    assert [p.phone async for p in contact.phonenumbers.all()] == ["3114"]
