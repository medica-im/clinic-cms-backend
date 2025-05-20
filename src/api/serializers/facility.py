import logging
import json
from typing import Union
from pydantic import ValidationError
from api.types.facility import Facility as FacilityPy
from api.types.organization_types import OrganizationTypePy
from api.types.organization import OrganizationPy
from api.types.geography import Commune as CommunePy, DepartmentOfFrance as DepartmentOfFrancePy
from neomodel import db
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
        label: str = "Organization",
        active: bool = True,
    ) -> FacilityPy:
    return get_facilities(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_facilities(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ) -> list[FacilityPy]:
    if uid:
            query=(
                f"""
                MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)
                WHERE f.uid="{uid}"
                RETURN f,c,dpt;
                """)
    else:
        if directory:
            query=(
                f"""
                MATCH (d:Directory) WHERE d.name="{directory.name}"
                WITH d
                MATCH (d)-[:HAS_ENTRY]->(entry:Entry)
                WITH entry
                MATCH (entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)
                RETURN DISTINCT f,c,dpt;
                """)
        else:
            query=(
                f"""
                MATCH (f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt:DepartmentOfFrance)
                RETURN DISTINCT f,c,dpt;
                """)
    #results, cols = db.cypher_query(query)
    q = db.cypher_query(query,resolve_objects = True)
    facilities: list[FacilityPy]=[]
    if q:
        for row in q[0]:
            logger.debug(row)
            (
                facility,
                commune,
                department,
            ) = row
            c=CommunePy.model_validate(commune)
            d=DepartmentOfFrancePy.model_validate(department)
            logger.debug(facility)
            logger.debug(c)
            logger.debug(d)
            try:
                f=FacilityPy.model_validate(facility)
                facilities.append(f)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return facilities

    
