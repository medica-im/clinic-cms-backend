import logging
import json
from django.core.cache import cache
from decimal import Decimal
from fastapi import HTTPException, Request
from typing import Union, TypedDict, Any
from pydantic import ValidationError, ConfigDict, TypeAdapter
from api.types.facility import FacilityPost, FacilityPut, Facility as FacilityPy
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune as CommunePy, DepartmentOfFrance as DepartmentOfFrancePy
from neomodel import db
from neomodel import adb
from neomodel.contrib.spatial_properties import NeomodelPoint, PointProperty
from directory.models.agraph import Commune, Facility
from api.utils import get_site_from_request, clear_cache

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
        active: bool = True,
    ) -> FacilityPy:
    try:
        facilities = await async_get_facilities(
            directory=directory,
            uid=uid,
            active=active
        )
        return facilities[0]
    except IndexError as e:
        logger.debug(e)
        raise HTTPException(status_code=404, detail=f"Facility {uid} not found")

async def async_get_facilities(
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
    q = await adb.cypher_query(query, resolve_objects = True)
    facilities: list[FacilityPy]=[]
    if q:
        for row in q[0]:
            [
                facility,
                commune,
                department,
                effectors,
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

async def create_facility(f: FacilityPost, request: Request)->FacilityPy:
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
    facility = await async_get_facility(uid=str(node.uid))
    await clear_cache("v1:facilities", request)
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
    return facility

async def delete_facility(uid: str)->dict:
    query=(
        f"""MATCH (f:Facility) WHERE f.uid="{uid}" RETURN f;"""
    )
    results, cols = await adb.cypher_query(query)
    logger.debug(f"{results=}\n{cols=}")
    if not results:
        raise HTTPException(status_code=404, detail="Facility not found")
    query=(
        f"""MATCH (f:Facility) WHERE f.uid="{uid}" DETACH DELETE f;"""
    )
    results, cols = await adb.cypher_query(query)
    logger.debug(f"{results=}\n{cols=}")
    return {"ok": True}
        