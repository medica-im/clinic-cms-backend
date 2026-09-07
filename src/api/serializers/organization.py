import logging
import json
from typing import Union
from pydantic import ValidationError
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune, DepartmentOfFrance
from neomodel import db
from directory.models import (
    Directory,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance
)

logger = logging.getLogger(__name__)

def get_organization(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ) -> OrganizationPy:
    return get_organizations(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_organizations(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ) -> list[OrganizationPy]:
    if uid:
        query=f"""MATCH (o:{label})-[:IS_A]->(t:OrganizationType),
        (o)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
        OPTIONAL MATCH (o)-[:OFFICIAL_WEBSITE]->(w:Website)
        OPTIONAL MATCH (o)-[:PART_OF]->(other:Organization)
        WHERE o.uid="{uid}"
        RETURN o,t,c,d,w,other;"""
    else:
        query=f"""MATCH (o:{label})-[:IS_A]->(t:OrganizationType),
        (o)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
        OPTIONAL MATCH (o)-[:OFFICIAL_WEBSITE]->(w:Website)
        OPTIONAL MATCH (o)-[:PART_OF]->(other:Organization)
        RETURN o,t,c,d,w,other;"""
    results, cols = db.cypher_query(query)
    orgs: list[OrganizationPy]=[]
    for row in results:
        org=Organization.inflate(row[cols.index('o')])
        org_dct=org.__properties__
        org_type=OrganizationType.inflate(row[cols.index('t')])
        org_type_dct=org_type.__properties__
        org_dct["type"]=org_type_dct
        commune=Commune.inflate(row[cols.index('c')])
        commune_dct=commune.__properties__
        dpt=DepartmentOfFrance.inflate(row[cols.index('d')])
        dpt_dct=dpt.__properties__
        commune_dct["department"]=dpt_dct
        org_dct["commune"]=commune_dct
        try:
            web=Website.inflate(row[cols.index('w')])
            web_dct=web.__properties__
        except TypeError:
            web_dct=None
        org_dct["website"]=web_dct
        try:
            other=Organization.inflate(row[cols.index('other')])
            other_dct=other.__properties__
        except TypeError:
            other_dct=None
        org_dct["organization"]=other_dct
        try:
            org=OrganizationPy.model_validate(org_dct)
            orgs.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return orgs

def create_organization(kwargs) -> OrganizationPy:
    node = Organization(
        name_fr=kwargs["name_fr"],
        label_fr=kwargs["label_fr"]
    ).save()
    commune=kwargs["commune"]
    if commune:
        try:
            commune_node = Commune.nodes.get(uid=commune)
            node.commune.connect(commune_node)
        except Exception as e:
            raise Exception(e)
    type = kwargs["type"]
    if type:
        try:
            organization_type=OrganizationType.nodes.get(uid=type)
            node.type.connect(organization_type)
        except Exception as e:
            raise Exception(e)
    organization = kwargs["organization"]
    if organization:
        try:
            organization_node=Organization.nodes.get(uid=organization)
            node.organization.connect(organization_node)
        except Exception as e:
            raise Exception(e)
    website_url=kwargs["website"]
    if website_url:
        try:
            website_node=Website.nodes.get(url=website_url)
        except Exception as e:
            website_node=Website(url=website_url).save()
        node.website.connect(website_node)
    org = get_organization(uid=str(node.uid))
    return org

def get_organization_type(
    directory: Directory|None = None,
    uid: str|None = None,
    active: bool = True) -> OrganizationTypePy:
    return get_organization_types(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_organization_types(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[OrganizationTypePy]:
    label: str = "OrganizationType"
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    nodes: list[OrganizationTypePy]=[]
    for row in results:
        org=OrganizationType.inflate(row[cols.index('n')])
        logger.debug(org.__dict__)
        logger.debug(org.__properties__)
        logger.debug(org)
        try:
            org_dct=org.__properties__
            org=OrganizationTypePy.model_validate(org_dct)
            logger.debug(org)
            nodes.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes

# ---------------------------------------------------------------------------
# The Django-side organisation payload, built on the event loop.
#
# The sync twin of this is facility.serializers.OrganizationSerializer, and it
# stays where it is — it still serves the DRF-side callers, and it remains the
# reference for the shape.
#
# What changes is the graph half: the walk runs on `adb`, so no part of it
# depends on the synchronous neomodel connection. That is not tidiness.
# neomodel's sync `Database` subclasses `_thread._local`, so a connection
# configured on one thread is invisible to the worker thread sync_to_async
# hands a serializer to. Every other v2 router — entries, facilities,
# effector_types, avatar, invitees — already reaches the graph through `adb`
# alone; this brings the last one into line.
#
# The Django half still goes through the existing DRF serializers, wrapped in
# sync_to_async. They touch only Django rows — no graph, no neomodel — so
# reusing them is safe and keeps one definition of each shape.
#
# tests/api/test_address_comes_from_the_graph.py pins the payload shape, the
# address included, key by key.
# ---------------------------------------------------------------------------

# Facility → Commune → Department → PublicHolidayZone, in one round trip.
# Every hop past the facility is optional: an organisation can exist before its
# commune is linked to a department, and the payload still has to render.
_ORGANIZATION_GRAPH_QUERY = """
MATCH (e:Entry {uid: $uid})-[:HAS_FACILITY]->(f:Facility)
OPTIONAL MATCH (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
OPTIONAL MATCH (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(d:DepartmentOfFrance)
OPTIONAL MATCH (d)-[:PART_OF]->(z:PublicHolidayZone)
RETURN f, c, d, z
LIMIT 1
"""


class _NoCountry:
    """get_address reads only `.name` off the country.

    The organisation payload has always served `country: None` — the country is
    not on the facility node and no caller reads it — so this preserves that
    answer while letting the shared get_address build the rest.
    """

    name = None


async def async_get_organization_nodes(neomodel_uid):
    """(facility, commune, department, zone) for an organisation's entry.

    All four come back None when the uid names no Entry node: an organisation
    can be created before its entry exists, and the payload still has to
    render rather than raise.
    """
    from neomodel import adb

    if not neomodel_uid:
        return None, None, None, None
    uid = neomodel_uid.hex if hasattr(neomodel_uid, "hex") else str(neomodel_uid)
    try:
        rows, _ = await adb.cypher_query(
            _ORGANIZATION_GRAPH_QUERY, {"uid": uid}, resolve_objects=True
        )
    except Exception as e:  # noqa: BLE001 - a broken graph must not 500 the page
        logger.error(f"{e}\n Cannot resolve the graph nodes for entry {uid}")
        return None, None, None, None
    if not rows:
        logger.error(f"Cannot find an Entry neo4j node with uid {uid}")
        return None, None, None, None
    return tuple(rows[0])


def get_organization_address(facility, commune, zone):
    """The address, from the shared get_address plus the holiday zone.

    get_address is the same function /api/v2/entries and /api/v2/fullentries
    build their address with, so this payload cannot drift from theirs. Only
    public_holidays_zone is added on top: it is four hops away and specific to
    this payload, and it is what the frontend's publicHolidaysStore reads.
    """
    from directory.utils import get_address

    if facility is None:
        return None
    address = get_address(facility, commune, _NoCountry())
    address["public_holidays_zone"] = zone.name if zone is not None else None
    return address


def get_organization_commune(commune):
    """The four keys the payload has always carried for the commune.

    Not `__properties__`: that also emits element_id_property, name_en and
    slug_en, which the sync serializer curated away and the frontend has never
    seen.
    """
    if commune is None:
        return None
    return {
        "uid": commune.uid,
        "name_fr": commune.name_fr,
        "slug_fr": commune.slug_fr,
        "wikidata": commune.wikidata,
    }


def get_organization_department(department):
    """As get_organization_commune, for the department."""
    if department is None:
        return None
    return {
        "uid": department.uid,
        "name": department.name,
        "code": department.code,
        "slug": department.slug,
        "wikidata": department.wikidata,
    }


async def async_get_django_organization(organization):
    """The whole /api/v2/organization payload as a plain dict."""
    from addressbook.api.serializers import ContactSerializer
    from facility.serializers import (
        CategorySerializer,
        CitySerializer,
        LegalEntitySerializer,
    )

    facility, commune, department, zone = await async_get_organization_nodes(
        organization.neomodel_uid
    )
    address = get_organization_address(facility, commune, zone)

    related = await _async_fetch_related(organization)

    contact = await _async_serialize(related["contact"], ContactSerializer) or {}
    # The address stays nested under `contact` rather than promoted to a field
    # of its own: the frontend reads organization.contact.address in the
    # footer, on the contact page and in publicHolidaysStore. Only its source
    # changes — an organisation with no Contact row still gets an address.
    contact["address"] = address

    return {
        "id": organization.id,
        "uid": organization.neomodel_uid.hex if organization.neomodel_uid else None,
        "name": organization.name,
        "company_name": organization.company_name,
        "language": organization.language,
        "formatted_name": organization.formatted_name,
        "formatted_name_short": organization.formatted_name_short,
        "formatted_name_definite_article": organization.formatted_name_definite_article,
        "website_title": organization.website_title,
        "website_description": organization.website_description,
        "category": await _async_serialize(related["category"], CategorySerializer),
        "contact": contact,
        "registration": organization.registration,
        "google_site_verification": organization.google_site_verification,
        "google_calendar_id": organization.google_calendar_id,
        "google_calendar_api_key": organization.google_calendar_api_key,
        "city": await _async_serialize(related["city"], CitySerializer),
        "commune": get_organization_commune(commune),
        "legal_entity": await _async_serialize(
            related["legal_entity"], LegalEntitySerializer
        ),
        "department": get_organization_department(department),
        # DRF's ImageField serialises to the file's URL, or None when no file
        # is set. Passing the FieldFile straight through would hand pydantic a
        # ThumbnailerImageFieldFile and fail validation at the boundary.
        "logo": organization.logo.url if organization.logo else None,
        "logo_alt": organization.logo_alt,
        "sandbox": organization.sandbox,
    }


async def _async_fetch_related(organization):
    """The four Django rows the payload nests, fetched with the async ORM.

    Django's own async tooling rather than a thread: `aget`/`afirst` issue the
    query on the event loop, so no part of the read needs sync_to_async. It
    also removes the dependency on the caller's select_related — a lazy
    attribute access here would raise SynchronousOnlyOperation the moment a
    caller forgot one, which is a trap that only springs in production.

    legal_entity is queried from LegalEntity rather than read off the
    organisation because it is the *reverse* side of a OneToOneField: the
    forward accessor raises RelatedObjectDoesNotExist when absent, while
    afirst() simply answers None.
    """
    from facility.models import LegalEntity

    return {
        "contact": await _aget_fk(organization, "contact"),
        "category": await _aget_fk(organization, "category"),
        "city": await _aget_fk(organization, "city"),
        "legal_entity": await LegalEntity.objects.filter(
            organization=organization
        ).afirst(),
    }


async def _aget_fk(instance, field_name):
    """A forward foreign key's row, or None, without touching the loop's rules.

    Read through the id column and a fresh queryset: `instance.<field>` would
    be a lazy read that raises SynchronousOnlyOperation unless the caller
    happened to select_related it.
    """
    related_id = getattr(instance, f"{field_name}_id", None)
    if related_id is None:
        return None
    model = instance._meta.get_field(field_name).related_model
    return await model.objects.filter(pk=related_id).afirst()


async def _async_serialize(instance, Serializer):
    """Render an already-fetched Django row through its DRF serializer.

    Every database read is done by the caller with Django's async ORM, so what
    is left in here is pure in-memory field rendering — no query, and nothing
    that could raise SynchronousOnlyOperation.

    It is still `sync_to_async`, because a DRF serializer is synchronous by
    construction and adrf does not change that: its `ato_representation` falls
    back to `sync_to_async(field.get_attribute)` and
    `sync_to_async(field.to_representation)` for every field that is not
    natively async, which is all of them here. Going through adrf would
    therefore not remove the thread hop but multiply it — ContactSerializer
    alone has eight fields, four of them nested list serializers at depth 3,
    so one hop for the whole serializer is strictly cheaper than one per field
    per row.
    """
    from asgiref.sync import sync_to_async

    if instance is None:
        return None
    return await sync_to_async(lambda: dict(Serializer(instance).data))()
