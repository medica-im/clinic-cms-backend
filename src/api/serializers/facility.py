import logging
import json
from typing import Union
from pydantic import ValidationError
from api.types.facility import Facility as FacilityPy
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune as CommunePy, DepartmentOfFrance as DepartmentOfFrancePy
from neomodel import db
from neomodel.contrib.spatial_properties import NeomodelPoint, PointProperty
from directory.models import (
    Directory,
    Facility,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance
)
logger = logging.getLogger(__name__)

def get_facility(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True,
    ) -> FacilityPy:
    try:
        return get_facilities(
            directory=directory,
            uid=uid,
            active=active
        )[0]
    except Exception as e:
        logger.debug(e)
        raise Exception(e)

def get_facilities(
        directory: Directory|None = None,
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
                MATCH (d:Directory) WHERE d.name="{directory.name}"
                WITH d
                MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
                WITH entry
                MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance), (e:Effector)-[]-(entry)-[]-(et:EffectorType)
                RETURN DISTINCT f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");
                """)
        else:
            query=(
                f"""
                MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance), (f)-[]-(entry:Entry), (e:Effector)-[]-(entry)-[]-(et:EffectorType)
                RETURN DISTINCT f,c,dpt,collect(e.name_fr+ " (" + et.name_fr + ")");
                """)
    q = db.cypher_query(query,resolve_objects = True)
    facilities: list[FacilityPy]=[]
    if q:
        for row in q[0]:
            logger.debug(row)
            (
                facility,
                commune,
                department,
                effectors,
            ) = row
            logger.debug(effectors)
            commune_dct = commune.__properties__
            commune_dct["department"]=department.__properties__
            logger.debug(facility)
            facility_dct=facility.__properties__
            logger.debug(facility_dct)
            location=facility.location
            logger.debug(location)
            facility_dct["commune"]=commune_dct
            facility_dct["effectors"]=effectors[0]
            facility_dct["location"]=location
            try:
                f=FacilityPy.model_validate(facility_dct)
                facilities.append(f)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return facilities

def create_facility(kwargs)->FacilityPy:
    logger.debug(kwargs["location"])
    try:
        longitude: int=kwargs["location"]["longitude"]
        logger.debug(longitude)
        latitude: int=kwargs["location"]["latitude"]
        logger.debug(latitude)
        lng_lat = (longitude,latitude)
        location=NeomodelPoint(lng_lat, crs='wgs-84')
        logger.debug(location)
    except Exception as e:
        logger.debug(e)
        location=None
    node = Facility(
        name=kwargs["name"],
        label=kwargs["label"],
        slug=kwargs["slug"],
        zoom=kwargs["zoom"],
        building=kwargs["building"],
        street=kwargs["street"],
        geographical_complement=kwargs["geographical_complement"],
        zip=kwargs["zip"],
        location=location
    ).save()
    commune=kwargs["commune"]
    if commune:
        try:
            commune_node = Commune.nodes.get(uid=commune)
            node.commune.connect(commune_node)
        except Exception as e:
            raise Exception(e)
    facility = get_facility(uid=str(node.uid))
    return facility
