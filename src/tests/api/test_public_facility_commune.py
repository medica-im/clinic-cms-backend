"""A public facility says which commune it is in, unambiguously.

The facility edit dialog centres its map on the commune and warns when a point
is far from it, which means looking the commune up in the national address
base (BAN). By name alone that is a guess: 1,450 commune names are shared in
France. Name and department code together leave two ambiguous pairs in the
whole country, so the payload carries the commune's uid and the code of its
department, read from the graph.
"""
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def facility_in_vedene(neo4j_graph, monkeypatch):
    import api.routers.public_facilities as public_facilities

    async def nothing(*args, **kwargs):
        return None

    # The address is under test, not the contact details around it.
    for name in ("async_get_phones_neomodel", "async_get_emails_neomodel",
                 "async_get_websites_neomodel", "async_get_socialnetworks_neomodel",
                 "async_get_avatar_url", "_get_place_image"):
        monkeypatch.setattr(public_facilities, name, nothing)

    ids = {k: uuid.uuid4().hex for k in ("facility", "commune", "department", "country")}
    await neo4j_graph.cypher_query(
        """
        CREATE (f:Facility {uid: $facility, name: 'Cabinet de Vedène', slug: 'cabinet-de-vedene'})
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid: $commune, name_fr: 'Vedène'})
        CREATE (d:DepartmentOfFrance {uid: $department, name: 'Vaucluse', code: '84'})
        CREATE (n:Country {uid: $country, name: 'France'})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
        CREATE (d)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(n)
        """,
        ids,
    )
    rows, _ = await neo4j_graph.cypher_query(
        """
        MATCH (f:Facility {uid: $facility})-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        MATCH (n:Country {uid: $country})
        RETURN f, c, n
        """,
        ids,
        resolve_objects=True,
    )
    return ids, rows[0]


async def test_it_names_the_commune_by_uid(facility_in_vedene):
    from api.routers.public_facilities import _serialize_facility

    ids, (facility, commune, country) = facility_in_vedene
    payload = await _serialize_facility(facility, commune, country)

    assert payload.commune == ids["commune"]


async def test_it_gives_the_department_code_of_the_commune(facility_in_vedene):
    from api.routers.public_facilities import _serialize_facility

    _, (facility, commune, country) = facility_in_vedene
    payload = await _serialize_facility(facility, commune, country)

    assert payload.address.city == "Vedène"
    assert payload.address.department_code == "84"
