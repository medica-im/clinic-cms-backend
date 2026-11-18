"""Gathering what the quality rules read, from the real graph and the address book.

The rules themselves are pure (tests/test_quality.py). What is pinned here is what they are
given: which entries a directory judges (active ones it lists, plus its unlisted porteurs),
that « immaterial » and « nature » come from the type, the porteur, the coverage and the
schedules from the graph, and the phones, emails and websites from the address book.
"""
import pytest

from directory.quality import directory_facts, directory_report, entry_facts

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: Contacts are keyed by a UUID, as real entry uids are.
LINE = "11111111111111111111111111111111"


@pytest.fixture
async def graph(neo4j_graph, transactional_db):
    await neo4j_graph.cypher_query(
        """
        CREATE (sm:Directory {name: 'sm'})-[:LISTS_NEED]->(need:Need {uid: 'n', slug: 'sante-mentale', name_fr: 'santé mentale'})
        CREATE (cond:Condition {uid: 'c', slug: 'mal-etre', name_fr: 'Mal-être'})-[:IMPACTS]->(need)
        CREATE (line_t:EffectorType {uid: 't-line', slug_fr: 'ligne-ecoute', name_fr: "ligne d'écoute", immaterial: true, nature: 'service'})
        CREATE (porteur_t:EffectorType {uid: 't-por', slug_fr: 'organisme-gestionnaire', name_fr: 'organisme gestionnaire', nature: 'service'})
        CREATE (hosp_t:EffectorType {uid: 't-hop', slug_fr: 'hopitaux', name_fr: 'hôpital', nature: 'service'})
        CREATE (d69:DepartmentOfFrance {uid: 'd-69', code: '69', name: 'Rhône'})

        CREATE (porteur:Entry {uid: 'porteur', slug: 'vinatier', active: true, siren: '266900083'})
        CREATE (porteur)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-p', name_fr: 'Centre hospitalier Le Vinatier', label_fr: 'Le Vinatier'})
        CREATE (porteur)-[:HAS_EFFECTOR_TYPE]->(porteur_t)
        CREATE (pf:Facility {uid: 'f-p', street: '95 Boulevard Pinel', zip: '69500', location: point({latitude: 45.7, longitude: 4.9, crs: 'wgs-84'})})
        CREATE (porteur)-[:HAS_FACILITY]->(pf)
        CREATE (sm)-[:HAS_ENTRY]->(porteur)

        CREATE (line:Entry {uid: $line, slug: '3114', active: true, description: 'Ligne nationale.', offers: ['listening'],
                            who_can_contact: 'anyone', care_levels: ['emergency'], access_modes: ['phone']})
        CREATE (line)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-l', name_fr: '3114 (Numéro national)', label_fr: 'Prévention suicide'})
        CREATE (line)-[:HAS_EFFECTOR_TYPE]->(line_t)
        CREATE (line)-[:HAS_FACILITY]->(pf)
        CREATE (line)-[:MANAGES]->(cond)
        CREATE (line)-[:RUN_BY]->(porteur)
        CREATE (line)-[:COVERS]->(d69)
        CREATE (line)-[:HAS_SCHEDULE]->(:Schedule {uid: 's1', channel: 'phone'})
        CREATE (sm)-[:HAS_ENTRY]->(line)

        CREATE (hosp:Entry {uid: 'hosp', slug: 'hopital', active: true})
        CREATE (hosp)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-h', name_fr: 'Hôpital X', label_fr: 'Hôpital X'})
        CREATE (hosp)-[:HAS_EFFECTOR_TYPE]->(hosp_t)
        CREATE (hosp)-[:HAS_FACILITY]->(:Facility {uid: 'f-h', zip: '69001'})
        CREATE (hosp)-[:MANAGES]->(cond)
        CREATE (sm)-[:HAS_ENTRY]->(hosp)

        CREATE (off:Entry {uid: 'off', slug: 'ferme', active: false})
        CREATE (off)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-o', name_fr: 'Fermé', label_fr: 'Fermé'})
        CREATE (off)-[:HAS_EFFECTOR_TYPE]->(hosp_t)
        CREATE (off)-[:HAS_FACILITY]->(pf)
        CREATE (off)-[:MANAGES]->(cond)
        CREATE (sm)-[:HAS_ENTRY]->(off)

        CREATE (other:Entry {uid: 'other', slug: 'ailleurs', active: true})
        CREATE (other)-[:HAS_EFFECTOR]->(:Effector {uid: 'x-a', name_fr: 'Ailleurs', label_fr: 'Ailleurs'})
        CREATE (other)-[:HAS_EFFECTOR_TYPE]->(hosp_t)
        CREATE (other)-[:HAS_FACILITY]->(pf)
        CREATE (:Directory {name: 'elsewhere'})-[:HAS_ENTRY]->(other)
        """,
        {"line": LINE},
    )
    return neo4j_graph


async def by_uid(directory="sm"):
    return {facts.uid: facts for facts in await directory_facts(directory)}


async def test_a_directory_judges_the_active_entries_it_holds_and_not_those_of_another(graph):
    facts = await by_uid()
    assert sorted(facts) == sorted([LINE, "hosp", "porteur"])


async def test_a_directory_that_lists_by_need_marks_what_it_lists_and_what_it_does_not(graph):
    facts = await by_uid()
    assert (facts[LINE].listed, facts["hosp"].listed, facts["porteur"].listed) == (True, True, False)


async def test_the_type_gives_immaterial_and_nature_and_the_entry_its_own_facts(graph):
    line = (await by_uid())[LINE]
    assert (line.type_slug, line.immaterial, line.nature) == ("ligne-ecoute", True, "service")
    assert (line.name, line.label, line.slug) == ("3114 (Numéro national)", "Prévention suicide", "3114")
    assert (line.description, line.offers, line.who_can_contact) == ("Ligne nationale.", ["listening"], "anyone")
    assert (line.care_levels, line.access_modes) == (["emergency"], ["phone"])


async def test_the_porteur_the_coverage_and_the_schedules_come_from_the_graph(graph):
    facts = await by_uid()
    assert (facts[LINE].has_porteur, facts[LINE].coverage, facts[LINE].schedules) == (True, 1, ["phone"])
    assert (facts["hosp"].has_porteur, facts["hosp"].coverage, facts["hosp"].schedules) == (False, 0, [])
    assert facts["porteur"].siren == "266900083"


async def test_a_facility_with_a_street_and_a_point_has_a_location_and_one_without_has_none(graph):
    facts = await by_uid()
    assert facts["porteur"].has_location is True
    assert facts["hosp"].has_location is False


async def test_the_contacts_come_from_the_address_book(graph):
    from addressbook.models import Contact, Email, PhoneNumber, Website

    contact = await Contact.objects.acreate(neomodel_uid=LINE)
    await PhoneNumber.objects.acreate(contact=contact, phone="3114", type="W")
    await Email.objects.acreate(contact=contact, email="a@b.fr")
    await Website.objects.acreate(contact=contact, url="https://x.fr")
    facts = await by_uid()
    assert (facts[LINE].phones, facts[LINE].emails, facts[LINE].websites) == (["3114"], ["a@b.fr"], ["https://x.fr"])
    assert (facts["hosp"].phones, facts["hosp"].emails, facts["hosp"].websites) == ([], [], [])


async def test_one_entry_is_gathered_the_same_way_as_in_the_directory(graph):
    one = await entry_facts(LINE, "sm")
    assert one == (await by_uid())[LINE]
    assert await entry_facts("nobody", "sm") is None


async def test_an_entry_is_listed_when_any_directory_holding_it_lists_it(graph):
    await graph.cypher_query(
        "MATCH (e:Entry {uid: 'porteur'}) CREATE (:Directory {name: 'open'})-[:HAS_ENTRY]->(e)"
    )
    assert (await entry_facts("porteur", "sm")).listed is False
    assert (await entry_facts("porteur")).listed is True


async def test_the_report_groups_the_entries_by_rule_with_what_is_missing_first(graph):
    report = await directory_report("sm")
    codes = [group["code"] for group in report]
    assert codes.index("no_contact") < codes.index("no_description")
    group = next(group for group in report if group["code"] == "no_contact")
    assert group["severity"] == "missing"
    assert [entry["slug"] for entry in group["entries"]] == ["3114", "hopital"]
    assert group["entries"][1]["type"] == "hôpital"
    assert not any(group["code"] == "porteur_without_siren" for group in report)
