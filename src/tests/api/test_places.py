"""Finding the places an entry may cover: a commune, a département, a region or the country.

Whoever sets where a service without premises answers types a few letters and picks: a
département by its name or its code, a commune with its département (six are called
Saint-Maurice), a region, France. Accents and case do not matter; what matches the
typed text exactly comes before what only starts or contains it. Public, like the
communes and départements it searches.
"""
import pytest

from directory.places import search_places

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (fr:Country {uid: 'fr', name: 'France', slug: 'france', code: 'FR'})
        CREATE (ara:RegionOfFrance {uid: 'ara', name: 'Auvergne-Rhône-Alpes', slug: 'auvergne-rhone-alpes', code: '84'})
        CREATE (idf:RegionOfFrance {uid: 'idf', name: 'Île-de-France', slug: 'ile-de-france', code: '11'})
        CREATE (d69:DepartmentOfFrance {uid: 'd69', name: 'Rhône', slug: 'rhone', code: '69'})
        CREATE (d01:DepartmentOfFrance {uid: 'd01', name: 'Ain', slug: 'ain', code: '01'})
        CREATE (d94:DepartmentOfFrance {uid: 'd94', name: 'Val-de-Marne', slug: 'val-de-marne', code: '94'})
        CREATE (d2a:DepartmentOfFrance {uid: 'd2a', name: 'Corse-du-Sud', slug: 'corse-du-sud', code: '2A'})
        CREATE (ara)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(fr)
        CREATE (idf)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(fr)
        CREATE (d69)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(ara)
        CREATE (d01)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(ara)
        CREATE (d94)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(idf)
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'lyon', name_fr: 'Lyon', slug_fr: 'lyon'})
            -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d69)
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'lyons', name_fr: 'Lyons-la-Forêt', slug_fr: 'lyons-la-foret'})
            -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d01)
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'sm94', name_fr: 'Saint-Maurice', slug_fr: 'saint-maurice'})
            -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d94)
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'sm01', name_fr: 'Saint-Maurice', slug_fr: 'saint-maurice'})
            -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d01)
        CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'isle', name_fr: "L'Isle-Adam", slug_fr: 'lisle-adam'})
            -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d94)
        """
    )
    return neo4j_graph


def uids(rows):
    return [row["uid"] for row in rows]


async def test_a_departement_is_found_by_its_name_whatever_the_accents_and_case(graph):
    for typed in ("Rhône", "rhone", "RHONE"):
        found = await search_places(typed)
        assert found[0] == {"uid": "d69", "name": "Rhône", "kind": "department", "code": "69", "department": None}


async def test_a_departement_is_found_by_its_code(graph):
    assert uids(await search_places("69"))[0] == "d69"
    assert uids(await search_places("2a"))[0] == "d2a"


async def test_homonym_communes_each_come_with_their_departement(graph):
    found = [row for row in await search_places("Saint-Maurice") if row["kind"] == "commune"]
    assert sorted((row["uid"], row["department"]) for row in found) == [("sm01", "01"), ("sm94", "94")]


async def test_the_country_and_a_region_are_found(graph):
    assert (await search_places("france"))[0] == {
        "uid": "fr", "name": "France", "kind": "country", "code": "FR", "department": None,
    }
    assert uids(await search_places("auvergne")) == ["ara"]


async def test_an_exact_name_comes_before_one_that_only_starts_with_it(graph):
    assert uids(await search_places("lyon")) == ["lyon", "lyons"]


async def test_a_name_with_an_apostrophe_is_found_as_typed(graph):
    assert uids(await search_places("L'Isle")) == ["isle"]


async def test_the_place_named_so_comes_before_the_one_whose_name_contains_it(graph):
    # « rhone » is the département's whole name and inside the region's.
    assert uids(await search_places("rhone")) == ["d69", "ara"]


async def test_a_code_names_a_departement_never_a_region(graph):
    # Regions have INSEE codes too, and 84 is both Auvergne-Rhône-Alpes and the Vaucluse:
    # nobody types a region's code.
    assert uids(await search_places("84")) == []


async def test_one_letter_finds_nothing(graph):
    assert await search_places("r") == []
    assert await search_places("  ") == []


async def test_the_list_is_capped(graph):
    await graph.cypher_query(
        "MATCH (d:DepartmentOfFrance {uid: 'd69'}) UNWIND range(1, 30) AS i "
        "CREATE (:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'v' + i, name_fr: 'Villeneuve ' + i, "
        "slug_fr: 'villeneuve-' + i})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)"
    )
    assert len(await search_places("villeneuve")) == 20


async def test_the_api_searches_without_signing_in(graph, client):
    response = await client.get("/places", params={"q": "rhone"})
    assert response.status_code == 200, response.text
    assert [row["uid"] for row in response.json()] == ["d69", "ara"]
