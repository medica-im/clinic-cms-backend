"""/api/v2/organization is served without touching the synchronous graph.

The endpoint was the last v2 router still built on a DRF serializer behind
`sync_to_async`. That is not merely slower: neomodel's sync `Database`
subclasses `_thread._local`, so the connection configured on one thread is
invisible to the worker thread `sync_to_async` runs the serializer on. Every
other v2 router — entries, facilities, effector_types, avatar, invitees —
reaches the graph through `adb` alone.

The payload is a contract. The frontend reads `organization.contact.address`
in the footer, on the contact page and in publicHolidaysStore, so these assert
the async builder answers exactly what the sync serializer answers, rather than
asserting the new code against itself.
"""
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


STREET = "12 rue de la Ré"
ZIP = "69002"
CITY = "Lyon"
ZONE = "Zone A"


@pytest.fixture
async def organization_entry(neo4j_graph):
    """An Entry with the full chain the payload walks, holiday zone included."""
    from neomodel import adb

    uid = uuid.uuid4().hex
    await adb.cypher_query(
        """
        CREATE (e:Entry {uid: $uid, active: true})
        CREATE (f:Facility {
            uid: $fuid, name: 'Maison', slug: 'maison',
            street: $street, zip: $zip, building: 'A',
            geographical_complement: '1er étage', zoom: 17,
            tooltip_text: 'ici', tooltip_permanent: true,
            location: point({latitude: 45.757, longitude: 4.832})
        })
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {
            uid: $cuid, name_fr: $city, slug_fr: 'lyon'
        })
        CREATE (d:DepartmentOfFrance {uid: $duid, name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q12724'})
        CREATE (z:PublicHolidayZone {uid: $zuid, name: $zone})
        CREATE (e)-[:HAS_FACILITY]->(f)
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d)
        CREATE (d)-[:PART_OF]->(z)
        """,
        {
            "uid": uid, "fuid": uuid.uuid4().hex, "cuid": uuid.uuid4().hex,
            "duid": uuid.uuid4().hex, "zuid": uuid.uuid4().hex,
            "street": STREET, "zip": ZIP, "city": CITY, "zone": ZONE,
        },
    )
    return uid


async def make_organization(entry_uid, *, with_contact=True):
    from asgiref.sync import sync_to_async

    @sync_to_async
    def build():
        from django.contrib.sites.models import Site
        from addressbook.models import Contact
        from facility.models import Organization

        suffix = uuid.uuid4().hex[:8]
        site, _ = Site.objects.get_or_create(
            domain=f"async-{suffix}.example", defaults={"name": "Async"}
        )
        contact = (
            Contact.objects.create(
                formatted_name="CPTS Async", neomodel_uid=uuid.UUID(entry_uid)
            )
            if with_contact
            else None
        )
        from facility.models import Category, LegalEntity

        category, _ = Category.objects.get_or_create(
            name="cpts",
            defaults={
                "formatted_name": "CPTS",
                "definition": "Communauté professionnelle",
                "slug": "cpts",
            },
        )
        organization = Organization.objects.create(
            name=f"cpts-async-{suffix}",
            company_name=f"CPTS Async {suffix}",
            formatted_name="CPTS Async",
            site=site,
            neomodel_uid=uuid.UUID(entry_uid),
            contact=contact,
            category=category,
        )
        # LegalEntity is owned by the organisation, so it can only exist once
        # the organisation does; the FK back the other way is what the payload
        # serialises.
        # SIREN, SIRET and the rest are unique and default to "", so each
        # legal entity needs its own or the second one collides.
        LegalEntity.objects.create(
            name=f"LE {suffix}",
            organization=organization,
            SIREN=suffix[:9],
            SIRET=f"{suffix}0000"[:14],
            RNA=f"W{suffix}",
            RCS=f"RCS{suffix}",
            VAT=f"FR{suffix}",
        )
        organization.refresh_from_db()
        return organization

    return await build()


class TestTheAsyncPayloadMatchesTheSyncOne:
    """The shape is unchanged; only the way the data is reached differs."""

    async def test_the_address_is_identical(self, organization_entry):
        from asgiref.sync import sync_to_async

        from api.serializers.organization import async_get_django_organization
        from facility.serializers import OrganizationSerializer

        org = await make_organization(organization_entry)

        async_payload = await async_get_django_organization(org)
        sync_payload = await sync_to_async(
            lambda: OrganizationSerializer(org).data
        )()

        assert async_payload["contact"]["address"] == sync_payload["contact"]["address"]

    async def test_the_holiday_zone_survives_the_four_hops(self, organization_entry):
        """Facility → Commune → Department → PublicHolidayZone.

        The async graph model had no PublicHolidayZone at all until this
        change, so the last hop had nothing to resolve to and the key would
        have serialised as null without anything failing.
        """
        from api.serializers.organization import async_get_django_organization

        org = await make_organization(organization_entry)
        payload = await async_get_django_organization(org)

        assert payload["contact"]["address"]["public_holidays_zone"] == ZONE

    async def test_the_commune_and_department_are_identical(self, organization_entry):
        from asgiref.sync import sync_to_async

        from api.serializers.organization import async_get_django_organization
        from facility.serializers import OrganizationSerializer

        org = await make_organization(organization_entry)

        async_payload = await async_get_django_organization(org)
        sync_payload = await sync_to_async(
            lambda: OrganizationSerializer(org).data
        )()

        for key in ("commune", "department"):
            assert async_payload[key] == sync_payload[key], f"{key} differs"

    async def test_an_organization_with_no_contact_row_still_has_an_address(
        self, organization_entry
    ):
        """Nothing about a facility's street requires a row in the addressbook."""
        from api.serializers.organization import async_get_django_organization

        org = await make_organization(organization_entry, with_contact=False)
        payload = await async_get_django_organization(org)

        assert payload["contact"]["address"]["street"] == STREET
        assert payload["contact"]["address"]["city"] == CITY

    async def test_an_entry_that_names_nothing_does_not_raise(self, neo4j_graph):
        """An organisation can exist before its entry does."""
        from api.serializers.organization import async_get_django_organization

        org = await make_organization(uuid.uuid4().hex)
        payload = await async_get_django_organization(org)

        assert payload["contact"]["address"] is None

    async def test_the_payload_validates_against_the_response_type(
        self, organization_entry
    ):
        """What the endpoint actually returns: model_validate is the boundary."""
        from api.serializers.organization import async_get_django_organization
        from api.types.organization import Organization as OrganizationPy

        org = await make_organization(organization_entry)
        payload = await async_get_django_organization(org)

        validated = OrganizationPy.model_validate(payload)
        assert validated.contact.address.street == STREET
        assert validated.contact.address.public_holidays_zone == ZONE


class TestItDoesNotUseTheSynchronousGraphConnection:
    """The point of the change, asserted rather than assumed."""

    async def test_the_builder_never_touches_neomodel_db(self, organization_entry):
        """`db` is the thread-local sync connection the worker thread loses.

        Patched to raise: if any part of the walk still reaches for it, this
        fails loudly instead of silently working on whichever thread happens
        to be configured.
        """
        from unittest.mock import patch

        from api.serializers.organization import async_get_django_organization

        org = await make_organization(organization_entry)

        def explode(*args, **kwargs):
            raise AssertionError(
                "the async organisation payload reached for the synchronous "
                "neomodel connection"
            )

        with patch("neomodel.db.cypher_query", side_effect=explode):
            payload = await async_get_django_organization(org)

        assert payload["contact"]["address"]["street"] == STREET
