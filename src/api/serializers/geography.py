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

def get_commune(
    directory: Directory|None = None,
    uid: str|None = None,
    active: bool = True) -> CommunePy:
    return get_communes(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_communes(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[CommunePy]:
    if uid:
        query=f"""MATCH (c:Commune) WHERE c.uid="{uid}" RETURN c;"""
    else:
        query=f"""MATCH (c:Commune) RETURN c;"""
    q = db.cypher_query(query, resolve_objects = True)
    nodes: list[CommunePy]=[]
    if q:
        for commune in q[0]:
            try:
                commune_dct=commune.__properties__
                commune=CommunePy.model_validate(commune_dct)
                logger.debug(commune)
                nodes.append(commune)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return nodes
