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
    """What /api/v2/organization serves.

    These assertions predate the refactor and were originally aimed at
    ContactSerializer.get_address(). The guarantees are unchanged — street,
    city, zip and the holiday zone still have to reach the payload — so they
    now go through OrganizationSerializer, which reads the organisation's own
    neomodel_uid rather than borrowing a Contact's.
    """

    @staticmethod
    async def serialise(entry_uid: str, *, with_contact: bool = False):
        from asgiref.sync import sync_to_async

        from facility.serializers import OrganizationSerializer

        @sync_to_async
        def build():
            from django.contrib.sites.models import Site
            from addressbook.models import Contact
            from facility.models import Organization

            suffix = uuid.uuid4().hex[:8]
            site, _ = Site.objects.get_or_create(
                domain=f"org-{suffix}.example", defaults={"name": "Org"}
            )
            contact = (
                Contact.objects.create(
                    formatted_name="CPTS", neomodel_uid=uuid.UUID(entry_uid)
                )
                if with_contact
                else None
            )
            organization = Organization.objects.create(
                name=f"cpts-{suffix}",
                formatted_name="CPTS",
                site=site,
                neomodel_uid=uuid.UUID(entry_uid),
                contact=contact,
            )
            return OrganizationSerializer(organization).data

        return await build()

    async def test_it_reads_the_address_from_the_entry_node(self, addressed_entry):
        data = await self.serialise(addressed_entry)
        address = data["contact"]["address"]

        assert address["street"] == STREET
        assert address["city"] == CITY
        assert address["zip"] == ZIP

    async def test_it_reports_the_public_holiday_zone(self, addressed_entry):
        """Four hops: Facility → Commune → Department → PublicHolidayZone.

        The frontend's publicHolidaysStore reads this to decide which school
        holiday calendar to show, and nothing else in the suite walks it.
        """
        data = await self.serialise(addressed_entry)

        assert data["contact"]["address"]["public_holidays_zone"] == ZONE

    async def test_an_organization_whose_uid_names_nothing_does_not_raise(
        self, neo4j_graph
    ):
        """No Entry node for this uid: no address, and no exception.

        An organisation can exist before its entry does, and the payload has to
        render either way.
        """
        data = await self.serialise(uuid.uuid4().hex)

        assert data["contact"]["address"] is None


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


class TestTheContactSerializerNoLongerBuildsAddresses:
    """ContactSerializer stopped answering a question it was never the source of.

    It carried a SerializerMethodField that read `contact.neomodel_uid`, walked
    Entry → Facility, and returned an address — the same walk
    OrganizationSerializer performs for commune and department, reached by a
    longer route. Once the organisation payload built its own address from the
    facility node, that method had no caller: OrganizationSerializer was the
    only one, and it overwrites the key.

    Removing it leaves the Contact serialising what is genuinely its own.
    """

    def test_it_no_longer_declares_an_address_field(self):
        from addressbook.api.serializers import ContactSerializer

        assert "address" not in ContactSerializer().fields, (
            "ContactSerializer still builds an address; the organisation "
            "payload overwrites it, so any value here is dead work at best "
            "and a second, divergent answer at worst"
        )

    def test_it_still_serialises_what_belongs_to_the_contact(self):
        """The rows that really do hang off a Contact stay.

        Emails, phone numbers, websites and social networks are addressbook
        data with no node behind them, which is why Organization.contact
        survives this change.
        """
        from addressbook.api.serializers import ContactSerializer

        fields = set(ContactSerializer().fields)
        for expected in (
            "emails", "phonenumbers", "websites", "socialnetworks",
            "formatted_name", "url",
        ):
            assert expected in fields, f"ContactSerializer lost {expected!r}"

    async def test_the_organization_payload_is_unaffected(self, addressed_entry):
        """The endpoint that used to depend on it still answers in full."""
        from asgiref.sync import sync_to_async

        from facility.serializers import OrganizationSerializer

        @sync_to_async
        def serialise():
            from django.contrib.sites.models import Site
            from addressbook.models import Contact
            from facility.models import Organization

            site, _ = Site.objects.get_or_create(
                domain=f"unaffected-{addressed_entry[:8]}.example",
                defaults={"name": "Unaffected"},
            )
            # With a Contact this time: its emails and phones still come from
            # the row, while the address comes from the graph.
            contact = Contact.objects.create(
                formatted_name="CPTS Unaffected",
                neomodel_uid=uuid.UUID(addressed_entry),
            )
            organization = Organization.objects.create(
                name=f"cpts-unaffected-{addressed_entry[:8]}",
                formatted_name="CPTS Unaffected",
                site=site,
                neomodel_uid=uuid.UUID(addressed_entry),
                contact=contact,
            )
            return OrganizationSerializer(organization).data

        data = await serialise()

        assert data["contact"]["address"]["street"] == STREET
        assert data["contact"]["formatted_name"] == "CPTS Unaffected"
        assert "emails" in data["contact"]


class TestTheAddressSerializerIsGone:
    """No serializer binds the addressbook Address model.

    AddressSerializer had no importer — grep finds nothing, no viewset names
    it, no router registers it and no dynamic lookup could reach it — but it
    declared `model = Address` in its Meta, which binds the model class at
    import time. That made it the one thing standing between the table and
    deletion: removing the model with this class present would break
    addressbook.api.serializers on import, and with it every module that
    imports that file.
    """

    def test_the_module_defines_no_address_serializer(self):
        from addressbook.api import serializers

        assert not hasattr(serializers, "AddressSerializer"), (
            "AddressSerializer is back; it binds addressbook.Address at import "
            "time, so the model cannot be dropped while it exists"
        )

    def test_no_serializer_still_binds_the_address_model(self):
        """The check that outlives this particular class name.

        Any ModelSerializer pointing at Address would block the drop just the
        same, whatever it were called.
        """
        import inspect

        from rest_framework import serializers as drf
        from addressbook.api import serializers
        from addressbook.models import Address

        bound = [
            name
            for name, member in inspect.getmembers(serializers, inspect.isclass)
            if issubclass(member, drf.ModelSerializer)
            and getattr(getattr(member, "Meta", None), "model", None) is Address
        ]
        assert bound == [], f"these serializers still bind Address: {bound}"

    def test_the_serializers_module_still_imports(self):
        """Everything else in the file survives the removal.

        ContactSerializer, PhoneNumberSerializer and the rest are imported by
        directory/utils.py on every request path.
        """
        from addressbook.api import serializers

        for expected in (
            "ContactSerializer", "PhoneNumberSerializer", "EmailSerializer",
            "WebsiteSerializer", "SocialNetworkSerializer", "ProfileSerializer",
        ):
            assert hasattr(serializers, expected), f"lost {expected}"
