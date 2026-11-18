"""Which facilities the public endpoints reach.

The map list follows the directory's listing rule: a facility only an unlisted
porteur sits at is not on the map. A facility's own page is reached by slug or uid
across every directory of the site, not only its default one: an entry of the
santé mentale directory has a facility page like any other, and a site never
reaches another site's facilities. As for the entry page, which looks the entry up
by slug without a directory filter, a page is reachable even when the list omits it.
"""
import pytest

from api.routers.public_facilities import _get_facility_nodes

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def graph(neo4j_graph):
    await neo4j_graph.cypher_query(
        """
        CREATE (country:Country {uid: 'fr'}), (dpt:DepartmentOfFrance {uid: 'd69'}), (commune:Commune:AdministrativeTerritorialEntityOfFrance {uid: 'lyon'})
        CREATE (commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (dpt)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (mental:Need {uid: 'n-sm'})
        CREATE (main:Directory {name: 'main'}), (sm:Directory {name: 'sm'}), (elsewhere:Directory {name: 'elsewhere'})
        CREATE (sm)-[:LISTS_NEED]->(mental)
        """
    )
    for uid, directory, active in [
        ("e-main", "main", True),
        ("e-sm", "sm", True),
        ("e-porteur", "sm", True),
        ("e-else", "elsewhere", True),
        ("e-off", "main", False),
    ]:
        await neo4j_graph.cypher_query(
            """
            MATCH (c:Commune {uid: 'lyon'}), (d:Directory {name: $directory})
            CREATE (e:Entry {uid: $uid, active: $active})-[:HAS_EFFECTOR]->(:Effector {uid: 'eff-' + $uid})
            CREATE (e)-[:HAS_FACILITY]->(f:Facility {uid: 'f-' + $uid, slug: 'slug-' + $uid})
                -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
            CREATE (d)-[:HAS_ENTRY]->(e)
            """,
            {"uid": uid, "directory": directory, "active": active},
        )
    await neo4j_graph.cypher_query(
        "MATCH (e:Entry {uid: 'e-sm'}), (n:Need {uid: 'n-sm'}) CREATE (e)-[:MANAGES]->(n)"
    )
    return neo4j_graph


async def slugs(rows):
    return sorted(facility.slug for facility, _commune, _country in rows)


async def test_a_facility_of_the_sites_other_directory_has_a_page(graph):
    rows = await _get_facility_nodes("main", slug="slug-e-sm", site_directories=["main", "sm"])
    assert await slugs(rows) == ["slug-e-sm"]
    rows = await _get_facility_nodes("main", uid="f-e-sm", site_directories=["main", "sm"])
    assert await slugs(rows) == ["slug-e-sm"]


async def test_without_the_site_directories_only_the_default_one_is_searched(graph):
    assert await _get_facility_nodes("main", slug="slug-e-sm") == []


async def test_another_sites_facility_is_never_reached(graph):
    assert await _get_facility_nodes("main", slug="slug-e-else", site_directories=["main", "sm"]) == []


async def test_a_facility_of_an_inactive_entry_has_no_page(graph):
    assert await _get_facility_nodes("main", slug="slug-e-off", site_directories=["main", "sm"]) == []


async def test_an_unlisted_porteurs_facility_has_a_page_but_is_not_on_the_map(graph):
    page = await _get_facility_nodes("sm", slug="slug-e-porteur", site_directories=["main", "sm"])
    assert await slugs(page) == ["slug-e-porteur"]
    assert await slugs(await _get_facility_nodes("sm")) == ["slug-e-sm"]


async def test_a_directory_without_the_edge_maps_all_its_active_facilities(graph):
    assert await slugs(await _get_facility_nodes("main")) == ["slug-e-main"]
