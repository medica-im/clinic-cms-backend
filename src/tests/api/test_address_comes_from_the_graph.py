"""Addresses are served from the graph, not from the addressbook table.

A facility's address used to be an `addressbook.Address` row. It is now
`street`, `zip`, `building`, `geographical_complement` and `location` on the
Facility node, and every path that serves an address resolves it there:

    /api/v2/entries          get_address(facility, commune, country)
    /api/v2/fullentries/…    get_address(facility, commune, country)
    /api/v2/organization     ContactSerializer.get_address(), which reads
                             contact.neomodel_uid and then walks
                             Entry → Facility itself

Nothing reads the table. These tests are what makes that claim checkable
before it is acted on: the point of writing them is to be able to drop
`addressbook.Address` and see the suite stay green, rather than to reason that
it should.

They seed a real graph rather than mocking the traversals, because the
traversals are the thing under test — `get_address` reaches through
`facility.commune.all()[0]` and, for the holiday zone, four hops to
`Commune → Department → PublicHolidayZone`. A mock would assert that the code
calls what it was written to call.
"""
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


STREET = "33 Cours Docteur Long"
ZIP = "69003"
CITY = "Lyon"
BUILDING = "Bâtiment B"
COMPLEMENT = "2e étage"
ZONE = "Zone A"


@pytest.fixture
async def addressed_entry(neo4j_graph):
    """An Entry whose Facility carries a full address and a holiday zone.

    Built through the whole chain the serializers walk — entry, effector,
    facility, commune, department, zone — because a shortcut here would leave
    the traversal untested, which is the half most likely to break when the
    table goes.
    """
    from neomodel import adb

    uid = uuid.uuid4().hex
    await adb.cypher_query(
        """
        CREATE (e:Entry {uid: $uid, slug: $slug, active: true, access: 'anonymous'})
        CREATE (f:Facility {
            uid: $facility_uid, name: 'Cabinet du Centre', slug: 'cabinet-du-centre',
            street: $street, zip: $zip, building: $building,
            geographical_complement: $complement,
            location: point({latitude: 45.749014, longitude: 4.882709})
        })
        // Both labels: Commune subclasses AdministrativeTerritorialEntityOfFrance,
        // and neomodel resolves a node by its full label set — one label alone
        // raises NodeClassNotDefined the moment resolve_objects loads it.
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid: $commune_uid, name_fr: $city, slug_fr: 'lyon'})
        CREATE (d:DepartmentOfFrance {uid: $department_uid, name: 'Rhône', code: '69'})
        CREATE (z:PublicHolidayZone {uid: $zone_uid, name: $zone})
        CREATE (e)-[:HAS_FACILITY]->(f)
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
        CREATE (d)-[:PART_OF]->(z)
        """,
        {
            "uid": uid,
            "slug": "cabinet-du-centre-mg-69",
            "facility_uid": uuid.uuid4().hex,
            "commune_uid": uuid.uuid4().hex,
            "department_uid": uuid.uuid4().hex,
            "zone_uid": uuid.uuid4().hex,
            "street": STREET,
            "zip": ZIP,
            "building": BUILDING,
            "complement": COMPLEMENT,
            "city": CITY,
            "zone": ZONE,
        },
    )
    return uid


async def fetch_facility_and_commune(entry_uid: str):
    """The nodes get_address takes, loaded the way the serializers load them."""
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        """
        MATCH (e:Entry {uid: $uid})-[:HAS_FACILITY]->(f:Facility)
        MATCH (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
        RETURN f, c
        """,
        {"uid": entry_uid},
        resolve_objects=True,
    )
    return rows[0][0], rows[0][1]


class FakeCountry:
    """get_address reads only `.name` from the country."""

    name = "France"


class TestTheEntryAddress:
    """What /api/v2/entries and /api/v2/fullentries serve.

    Both build their `address` with the same `get_address`, so one set of
    assertions covers the pair.
    """

    async def test_it_reads_the_street_from_the_facility_node(
        self, addressed_entry
    ):
        from directory.utils import get_address

        facility, commune = await fetch_facility_and_commune(addressed_entry)
        address = get_address(facility, commune, FakeCountry())

        assert address["street"] == STREET
        assert address["zip"] == ZIP
        assert address["building"] == BUILDING
        assert address["geographical_complement"] == COMPLEMENT

    async def test_the_city_comes_from_the_commune_it_is_linked_to(
        self, addressed_entry
    ):
        """Not a column on the facility: a hop to the Commune node."""
        from directory.utils import get_address

        facility, commune = await fetch_facility_and_commune(addressed_entry)
        address = get_address(facility, commune, FakeCountry())

        assert address["city"] == CITY

    async def test_the_coordinates_come_from_the_facility_point(
        self, addressed_entry
    ):
        """`location` is a Neo4j point, unpacked into latitude/longitude.

        The map markers read these, so a change of storage that dropped them
        would leave every entry unplotted rather than visibly broken.
        """
        from directory.utils import get_address

        facility, commune = await fetch_facility_and_commune(addressed_entry)
        address = get_address(facility, commune, FakeCountry())

        assert round(address["latitude"], 4) == 45.7490
        assert round(address["longitude"], 4) == 4.8827

    async def test_a_facility_with_no_point_still_answers(self, neo4j_graph):
        """Missing coordinates are None, not an exception.

        get_address branches on `facility.location` for exactly this, and an
        entry can be created before anyone geocodes it.
        """
        from neomodel import adb

        from directory.utils import get_address

        uid = uuid.uuid4().hex
        await adb.cypher_query(
            """
            CREATE (e:Entry {uid: $uid, active: true})
            CREATE (f:Facility {uid: $fuid, street: 'rue Sans Point', zip: '69001'})
            CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid: $cuid, name_fr: 'Lyon'})
            CREATE (e)-[:HAS_FACILITY]->(f)
            CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
            """,
            {"uid": uid, "fuid": uuid.uuid4().hex, "cuid": uuid.uuid4().hex},
        )

        facility, commune = await fetch_facility_and_commune(uid)
        address = get_address(facility, commune, FakeCountry())

        assert address["latitude"] is None
        assert address["longitude"] is None
        assert address["street"] == "rue Sans Point"

    async def test_no_field_is_read_from_the_addressbook(self, addressed_entry):
        """Every key get_address returns comes from a node.

        The assertion that makes dropping addressbook.Address safe: seeding
        only graph nodes produces a complete address, so there is nothing the
        table could still be supplying.
        """
        from directory.utils import get_address

        facility, commune = await fetch_facility_and_commune(addressed_entry)
        address = get_address(facility, commune, FakeCountry())

        for key in ("street", "zip", "building", "city", "facility_uid"):
            assert address[key], f"{key} is empty although only nodes were seeded"


class TestTheOrganizationAddress:
    """What /api/v2/organization serves, through ContactSerializer.

    The organisation's address takes a longer route — Organization.contact, a
    Django row, whose `neomodel_uid` names the Entry node the address is then
    read from. The Contact supplies the identifier and none of the data, which
    is why the table behind it can go.
    """

    async def test_it_reads_the_address_through_the_contacts_node_uid(
        self, addressed_entry
    ):
        from asgiref.sync import sync_to_async

        from addressbook.api.serializers import ContactSerializer
        from addressbook.models import Contact

        @sync_to_async
        def serialise():
            contact = Contact.objects.create(
                formatted_name="CPTS Lyon 3",
                neomodel_uid=uuid.UUID(addressed_entry),
            )
            return ContactSerializer(contact).data["address"]

        address = await serialise()

        assert address["street"] == STREET
        assert address["city"] == CITY
        assert address["zip"] == ZIP

    async def test_it_reports_the_public_holiday_zone(self, addressed_entry):
        """Four hops: Facility → Commune → Department → PublicHolidayZone.

        The frontend's publicHolidaysStore reads this to decide which school
        holiday calendar to show, and nothing else in the suite walks it.
        """
        from asgiref.sync import sync_to_async

        from addressbook.api.serializers import ContactSerializer
        from addressbook.models import Contact

        @sync_to_async
        def serialise():
            contact = Contact.objects.create(
                formatted_name="CPTS Lyon 3",
                neomodel_uid=uuid.UUID(addressed_entry),
            )
            return ContactSerializer(contact).data["address"]

        assert (await serialise())["public_holidays_zone"] == ZONE

    async def test_a_contact_with_no_node_does_not_raise(self, neo4j_graph):
        """A Contact whose neomodel_uid names nothing yields no address.

        Not an error: contacts exist that were never linked to an entry, and
        the organisation payload has to render without one.
        """
        from asgiref.sync import sync_to_async

        from addressbook.api.serializers import ContactSerializer
        from addressbook.models import Contact

        @sync_to_async
        def serialise():
            contact = Contact.objects.create(
                formatted_name="Orpheline", neomodel_uid=uuid.uuid4()
            )
            return ContactSerializer(contact).data["address"]

        assert await serialise() is None


class TestTheOrganizationSerializerNeedsNoContactRow:
    """The organisation's address is reachable without a Contact.

    OrganizationSerializer already walks Entry → Facility → Commune →
    Department itself, for `commune` and `department`. The address took a
    different route to the same nodes: through Organization.contact, a Django
    row whose only contribution was `neomodel_uid` — the identifier the
    serializer already holds on `obj.neomodel_uid`.

    These pin the outcome of removing that detour. The payload keeps the
    address nested under `contact`, because the frontend reads
    `organization.contact.address` in the footer, the contact page and
    publicHolidaysStore; only its source changes.
    """

    async def test_the_address_is_built_from_the_organizations_own_node(
        self, addressed_entry
    ):
        """No Contact row exists in this test, and the address still resolves."""
        from asgiref.sync import sync_to_async

        from facility.serializers import OrganizationSerializer

        @sync_to_async
        def serialise():
            from django.contrib.sites.models import Site
            from facility.models import Organization

            site, _ = Site.objects.get_or_create(
                domain=f"address-{addressed_entry[:8]}.example",
                defaults={"name": "Address Test"},
            )
            organization = Organization.objects.create(
                name=f"cpts-address-{addressed_entry[:8]}",
                formatted_name="CPTS Address Test",
                site=site,
                neomodel_uid=uuid.UUID(addressed_entry),
                contact=None,
            )
            return OrganizationSerializer(organization).data

        data = await serialise()
        address = (data.get("contact") or {}).get("address")

        assert address is not None, (
            "the organisation has no Contact row, and the address has to come "
            "from its own neomodel_uid"
        )
        assert address["street"] == STREET
        assert address["city"] == CITY

    async def test_it_keeps_the_shape_the_frontend_reads(self, addressed_entry):
        """organization.contact.address, with every key it had before.

        The footer reads street and city, publicHolidaysStore reads
        public_holidays_zone, and the map reads latitude/longitude — so the
        keys are the contract, not an implementation detail.
        """
        from asgiref.sync import sync_to_async

        from facility.serializers import OrganizationSerializer

        @sync_to_async
        def serialise():
            from django.contrib.sites.models import Site
            from facility.models import Organization

            site, _ = Site.objects.get_or_create(
                domain=f"shape-{addressed_entry[:8]}.example",
                defaults={"name": "Shape"},
            )
            organization = Organization.objects.create(
                name=f"cpts-shape-{addressed_entry[:8]}",
                formatted_name="CPTS Shape Test",
                site=site,
                neomodel_uid=uuid.UUID(addressed_entry),
                contact=None,
            )
            return OrganizationSerializer(organization).data

        address = (await serialise())["contact"]["address"]

        for key in (
            "building", "city", "country", "facility_uid",
            "geographical_complement", "latitude", "longitude",
            "public_holidays_zone", "street", "tooltip_direction",
            "tooltip_permanent", "tooltip_text", "zip", "zoom",
        ):
            assert key in address, f"the payload lost {key!r}"
