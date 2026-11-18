"""A facility without coordinates is stored without a point, never at 0/0.

The facility forms used to send latitude=0, longitude=0 whenever the geocoder
was not used, and the API stored that as a real point: a pin in the Gulf of
Guinea on every directory map. No facility of ours is at 0/0, so the pair means
"unknown" and is stored as such. A lone coordinate is a malformed request.
"""
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.types.facility import FacilityPost, FacilityPut


BASE = {
    "name": "Cabinet Sans Point",
    "label": None,
    "slug": "cabinet-sans-point",
    "building": None,
    "street": "rue Sans Point",
    "geographical_complement": None,
    "zip": "69003",
    "ban_id": None,
    "ban_banId": None,
}


def put(**coordinates) -> FacilityPut:
    return FacilityPut(**BASE, **coordinates)


def post(**coordinates) -> FacilityPost:
    return FacilityPost(**BASE, commune=uuid.uuid4().hex, **coordinates)


@pytest.mark.parametrize("build", [put, post], ids=["put", "post"])
class TestTheRequestTypes:
    def test_null_coordinates_stay_null(self, build):
        f = build(latitude=None, longitude=None)
        assert (f.latitude, f.longitude) == (None, None)

    def test_missing_coordinates_are_null(self, build):
        f = build()
        assert (f.latitude, f.longitude) == (None, None)

    @pytest.mark.parametrize("zero", [0, "0", "0.0", Decimal("0")])
    def test_zero_zero_becomes_null(self, build, zero):
        f = build(latitude=zero, longitude=zero)
        assert (f.latitude, f.longitude) == (None, None)

    def test_a_real_point_is_kept(self, build):
        f = build(latitude="45.749014", longitude="4.882709")
        assert f.latitude == Decimal("45.749014")
        assert f.longitude == Decimal("4.882709")

    def test_a_point_on_one_axis_only_is_kept(self, build):
        """Only the pair 0/0 is meaningless; the equator and Greenwich are real."""
        f = build(latitude="0", longitude="4.882709")
        assert f.latitude == Decimal("0")

    @pytest.mark.parametrize(
        "coordinates",
        [{"latitude": "45.75"}, {"longitude": "4.88"},
         {"latitude": "45.75", "longitude": None}],
        ids=["latitude-only", "longitude-only", "longitude-null"],
    )
    def test_a_lone_coordinate_is_refused(self, build, coordinates):
        with pytest.raises(ValidationError):
            build(**coordinates)


class TestTheLocationHelper:
    """The one place both writers turn a request into a Neo4j point."""

    def test_no_coordinates_give_no_point(self):
        from api.serializers.facility import location_from

        assert location_from(put()) is None

    def test_coordinates_give_a_wgs84_point(self):
        from api.serializers.facility import location_from

        point = location_from(put(latitude="45.749014", longitude="4.882709"))
        assert round(point.latitude, 4) == 45.7490
        assert round(point.longitude, 4) == 4.8827
        assert point.crs == "wgs-84"

    def test_both_writers_use_it(self):
        import inspect

        import api.serializers.facility as facility_serializers

        for writer in (facility_serializers.create_facility,
                       facility_serializers.update_facility):
            source = inspect.getsource(writer)
            assert "location_from(" in source, writer.__name__
            assert "NeomodelPoint(" not in source, writer.__name__


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdatingAFacility:
    """PUT /api/v2/facilities/{uid}, run against a real graph."""

    @pytest.fixture
    async def located_facility(self, neo4j_graph, monkeypatch):
        from neomodel import adb

        import api.serializers.facility as facility_serializers

        async def nothing(*args, **kwargs):
            return None

        # Neither is about coordinates: the slug guard needs a Site and an
        # Organization, the cache clear needs redis.
        monkeypatch.setattr(facility_serializers, "assert_slug_is_free", nothing)
        monkeypatch.setattr(facility_serializers, "clear_cache", nothing)

        uid = uuid.uuid4().hex
        await adb.cypher_query(
            """
            CREATE (f:Facility {
                uid: $uid, name: 'Cabinet Sans Point', slug: 'cabinet-sans-point',
                street: 'rue Sans Point', zip: '69003',
                location: point({latitude: 45.749014, longitude: 4.882709})
            })
            CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {
                uid: $cuid, name_fr: 'Lyon', slug_fr: 'lyon'
            })
            CREATE (d:DepartmentOfFrance {
                uid: $duid, name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q46130'
            })
            CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
            CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
            """,
            {"uid": uid, "cuid": uuid.uuid4().hex, "duid": uuid.uuid4().hex},
        )
        return uid

    async def stored_location(self, uid):
        from neomodel import adb

        rows, _ = await adb.cypher_query(
            "MATCH (f:Facility {uid: $uid}) RETURN f.location", {"uid": uid}
        )
        return rows[0][0]

    async def test_null_removes_the_point(self, located_facility):
        from api.serializers.facility import update_facility

        facility = await update_facility(
            located_facility, put(latitude=None, longitude=None), request=None
        )

        assert await self.stored_location(located_facility) is None
        assert facility.location is None

    async def test_zero_zero_removes_the_point(self, located_facility):
        from api.serializers.facility import update_facility

        await update_facility(
            located_facility, put(latitude=0, longitude=0), request=None
        )

        assert await self.stored_location(located_facility) is None

    async def test_a_new_point_is_stored(self, located_facility):
        from api.serializers.facility import update_facility

        facility = await update_facility(
            located_facility,
            put(latitude="43.9536", longitude="4.8790"),
            request=None,
        )

        stored = await self.stored_location(located_facility)
        assert round(stored.y, 4) == 43.9536
        assert round(stored.x, 4) == 4.8790
        assert round(facility.location.latitude, 4) == 43.9536
