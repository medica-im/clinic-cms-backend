import logging
import json
from django.core.cache import cache
from decimal import Decimal
from fastapi import HTTPException, Request, status
from typing import Union, TypedDict, Any
from pydantic import ValidationError, ConfigDict, TypeAdapter
from api.types.facility import FacilityPost, FacilityPut, Facility as FacilityPy
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune as CommunePy, DepartmentOfFrance as DepartmentOfFrancePy
from neomodel import db
from neomodel import adb
from neomodel.contrib.spatial_properties import NeomodelPoint, PointProperty
from directory.models.agraph import Commune, Facility, Entry
from api.utils import get_site_from_request, clear_cache
from api.neo4j_auth import get_neo4j_user
from api.auth import verify_user_access
from facility.models import Organization

logger = logging.getLogger(__name__)

def get_facility(
        directory: str|None = None,
        uid: str|None = None,
        active: bool = True,
    ) -> FacilityPy:
    try:
        return get_facilities(
            directory=directory,
            uid=uid,
            active=active
        )[0]
    except IndexError as e:
        logger.debug(e)
        raise HTTPException(status_code=404, detail=f"Facility {uid} not found")

def get_facilities(
        directory: str|None = None,
        uid: str|None = None,
        active: bool = True,
    ) -> list[FacilityPy]:
    if uid:
            query=(
                f"""MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance) WHERE f.uid="{uid}" WITH f,c,dpt OPTIONAL MATCH (f)-[]-(entry:Entry), (e:Effector)-[]-(entry)-[]-(et:EffectorType) RETURN f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");""")
    else:
        if directory:
            query=(
                f"""
                MATCH (d:Directory) WHERE d.name="{directory}"
                WITH d
                MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
                WITH entry
                MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance), (e:Effector)-[]-(entry)-[]-(et:EffectorType)
                RETURN DISTINCT f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");
                """)
        else:
            query=(
                f"""
                MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance) OPTIONAL MATCH (f)-[]-(entry:Entry), (e:Effector)-[]-(entry)-[]-(et:EffectorType)
                RETURN DISTINCT f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");
                """)
    q = db.cypher_query(query,resolve_objects = True)
    facilities: list[FacilityPy]=[]
    if q:
        for row in q[0]:
            (
                facility,
                commune,
                department,
                effectors,
            ) = row
            commune_dct = commune.__properties__
            commune_dct["department"]=department.__properties__
            facility_dct=facility.__properties__
            point=facility.location
            try:
                location_dct={"longitude": point.longitude, "latitude": point.latitude}
            except:
                location_dct=None
            facility_dct["commune"]=commune_dct
            facility_dct["effectors"]=effectors[0]
            facility_dct["location"]=location_dct
            try:
                f=FacilityPy.model_validate(facility_dct)
                facilities.append(f)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return facilities

async def async_get_facility(
        directory: str|None = None,
        uid: str|None = None,
        slug: str|None = None,
        active: bool = True,
    ) -> FacilityPy:
    try:
        facilities = await async_get_facilities(
            directory=directory,
            uid=uid,
            slug=slug,
            active=active
        )
        return facilities[0]
    except IndexError as e:
        logger.debug(e)
        detail = f"Facility {slug or uid} not found"
        raise HTTPException(status_code=404, detail=detail)

async def async_get_facilities(
        directory: str|None = None,
        uid: str|None = None,
        slug: str|None = None,
        entry_uid: str|None = None,
        active: bool = True,
    ) -> list[FacilityPy]:
    if uid:
            query=(
                f"""MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance) WHERE f.uid="{uid}" WITH f,c,dpt OPTIONAL MATCH (f)-[]-(entry:Entry), (e:Effector)-[]-(entry)-[]-(et:EffectorType) RETURN f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");""")
    elif slug:
            query=(
                f"""MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance) WHERE f.slug="{slug}" WITH f,c,dpt OPTIONAL MATCH (f)-[]-(entry:Entry), (e:Effector)-[]-(entry)-[]-(et:EffectorType) RETURN f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");""")
    elif entry_uid:
        query=(
            f"""
            MATCH (org_entry:Entry {{uid: "{entry_uid}"}})<-[:PART_OF]-(f:Facility)
                  -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)
                  -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)
            OPTIONAL MATCH (f)<-[:HAS_FACILITY]-(entry:Entry)<-[:HAS_EFFECTOR]-(e:Effector)-[:IS_A]->(et:EffectorType)
            RETURN DISTINCT f, c, dpt, collect(e.name_fr + " (" + et.name_fr + ")");
            """)
    else:
        if directory:
            query=(
                f"""
                MATCH (d:Directory) WHERE d.name="{directory}"
                WITH d
                MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
                WITH entry
                MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance), (e:Effector)-[]-(entry)-[]-(et:EffectorType)
                RETURN DISTINCT f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");
                """)
        else:
            query=(
                f"""
                MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)
                OPTIONAL MATCH (f)<-[:HAS_FACILITY]-(entry:Entry)<-[:HAS_EFFECTOR]-(e:Effector)-[:IS_A]->(et:EffectorType)
                RETURN DISTINCT f, c, dpt, collect(e.name_fr + " (" + et.name_fr + ")");
                """)
    q = await adb.cypher_query(query, resolve_objects = True)
    facilities: list[FacilityPy]=[]
    if q:
        for row in q[0]:
            [
                facility,
                commune,
                department,
                [effectors],
            ] = row
            logger.debug(f"{effectors=}")
            commune_dct = commune.__properties__
            commune_dct["department"]=department.__properties__
            facility_dct=facility.__properties__
            point=facility.location
            try:
                location_dct={"longitude": point.longitude, "latitude": point.latitude}
            except:
                location_dct=None
            facility_dct["commune"]=commune_dct
            facility_dct["effectors"]=effectors
            facility_dct["location"]=location_dct
            try:
                f=FacilityPy.model_validate(facility_dct)
                logger.debug(f"{f=}")
                facilities.append(f)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return facilities

async def assert_slug_is_free(
    slug: str | None,
    request: Request,
    exclude_uid: str | None = None,
) -> None:
    """
    Refuse a slug another facility of the same organization already holds.

    A facility is addressed by its slug — /sites/{slug}, and
    /api/v2/public/facilities/{slug}, which returns rows[0]. Two facilities of
    one organization sharing a slug make one of them unreachable: the graph
    answers with whichever it finds first, every time, and the other has no
    address at all. Twenty slugs are shared across the development graph and
    four of those are real clashes within a single organization, "cabinet-
    infirmier" among them, held three times over.

    Scoped per organization rather than globally, and deliberately not a
    neomodel `unique_index=True`, which cannot express the scope: "cabinet-
    medical" and "pharmacie" are ordinary names, two unrelated organizations
    are each entitled to one, and the public endpoint already filters by the
    requesting site's directory so it could never confuse them.

    PART_OF is the edge that attaches a facility to its organization — to an
    Organization node, or to that organization's Entry, both of which
    create_facility itself writes.

    `exclude_uid` is the facility being edited: keeping its own slug through an
    update is not a clash.
    """
    if not slug:
        return

    site = await get_site_from_request(request)
    try:
        org = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        # No organization for this site: nothing to scope against, so there is
        # no clash to report. The write is the caller's business.
        return
    if not org.neomodel_uid:
        return

    org_uid = org.neomodel_uid.hex
    results, _ = await adb.cypher_query(
        """
        MATCH (other:Facility)-[:PART_OF]->(o)
        WHERE o.uid = $org_uid
          AND other.slug = $slug
          AND ($exclude IS NULL OR other.uid <> $exclude)
        RETURN other.uid, other.name
        LIMIT 1
        """,
        {"org_uid": org_uid, "slug": slug, "exclude": exclude_uid},
    )
    if results:
        other_uid, other_name = results[0][0], results[0][1]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The slug '{slug}' is already used by the facility "
                f"'{other_name or other_uid}'. Facility addresses must be "
                "unique within an organization."
            ),
        )


async def create_facility(f: FacilityPost, request: Request, jwt: dict)->FacilityPy:
    try:
        longitude: Decimal|None = f.longitude
        logger.debug(longitude)
        latitude: Decimal|None = f.latitude
        logger.debug(latitude)
        lng_lat = (longitude,latitude)
        location=NeomodelPoint(lng_lat, crs='wgs-84')
        logger.debug(location)
    except Exception as e:
        logger.debug(e)
        location=None
    await assert_slug_is_free(f.slug, request)
    node = await Facility(
        name=f.name,
        label=f.label,
        slug=f.slug,
        zoom=f.zoom,
        building=f.building,
        street=f.street,
        geographical_complement=f.geographical_complement,
        zip=f.zip,
        ban_id=f.ban_id,
        ban_banId=f.ban_banId,
        location=location
    ).save()
    commune=f.commune
    if commune:
        try:
            commune_node = await Commune.nodes.get(uid=commune)
            await node.commune.connect(commune_node)
        except Exception as e:
            raise Exception(e)
    neo4j_user = await get_neo4j_user(jwt)
    if neo4j_user:
        await node.creator.connect(neo4j_user)
        await node.owner.connect(neo4j_user)
    # Connect facility to the organization's Entry via PART_OF
    site = await get_site_from_request(request)
    org = await Organization.objects.aget(site=site)
    if org.neomodel_uid:
        entry_uid = org.neomodel_uid.hex
        await verify_user_access(jwt, entry_uid)
        await adb.cypher_query(
            "MATCH (f:Facility {uid: $f_uid}), (e:Entry {uid: $e_uid}) "
            "MERGE (f)-[:PART_OF]->(e)",
            {"f_uid": node.uid, "e_uid": entry_uid},
        )
    facility = await async_get_facility(uid=str(node.uid))
    await clear_cache("v1:facilities", request)
    await clear_cache("v2:public/facilities", request)
    # A new facility is a new pin, reached the same way as a moved one.
    await clear_cache("v2:entries", request)
    return facility

async def update_facility(uid: str, f: FacilityPut, request: Request)->FacilityPy:
    try:
        longitude: Decimal|None = f.longitude
        logger.debug(longitude)
        latitude: Decimal|None = f.latitude
        logger.debug(latitude)
        lng_lat = (longitude,latitude)
        location=NeomodelPoint(lng_lat, crs='wgs-84')
        logger.debug(location)
    except Exception as e:
        logger.debug(e)
        location=None
    try:
        node = await Facility.nodes.get(uid=uid)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail=f"Facility with uid={uid} not found.")
    await assert_slug_is_free(f.slug, request, exclude_uid=uid)
    node.name=f.name
    node.label=f.label
    node.slug=f.slug
    node.zoom=f.zoom
    node.building=f.building
    node.street=f.street
    node.geographical_complement=f.geographical_complement
    node.zip=f.zip
    node.ban_id=f.ban_id
    node.ban_banId=f.ban_banId
    node.location=location
    await node.save()
    facility = await async_get_facility(uid=uid)
    await clear_cache("v1:facilities", request)
    await clear_cache("v2:public/facilities", request)
    # The entries payload carries each entry's address, coordinates included,
    # and the directory map plots those rather than the facility record. Without
    # this a facility moved in the edit modal keeps its old pin on the annuaire
    # until the entries TTL expires, while /sites/{slug} already shows the new
    # one. See tests/api/test_facility_edit_clears_the_entries_cache.py.
    await clear_cache("v2:entries", request)
    return facility

async def delete_facility(uid: str)->dict:
    try:
        facility_node = await Facility.nodes.get(uid=uid)
    except Facility.DoesNotExist:
        raise HTTPException(status_code=404, detail="Facility not found")
    # Any linked entry blocks the deletion, deactivated ones included:
    # deactivation is reversible and keeps the entry's history, so an entry that
    # still names this address must be deleted outright before the address can
    # go. Otherwise reactivating it would resurrect a facility that no longer
    # exists.
    #
    # This is not a permission: it does not depend on who is asking, and a
    # superuser is refused just the same. The objection is to the state of the
    # data, so it belongs here rather than in AccessControl.
    entries = await facility_node.entries.all()
    if entries:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Facility is still used by {len(entries)} "
                f"{'entry' if len(entries) == 1 else 'entries'} and cannot be deleted"
            )
        )
    await facility_node.delete()
    return {"ok": True}
        
