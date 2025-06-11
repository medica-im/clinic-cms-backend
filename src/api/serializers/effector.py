import logging
from neomodel import db
from pydantic import ValidationError
from directory.models import (
    Directory,
    Facility,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance
)
from directory.models import Effector as EffectorNeo4j
from api.types.effector import Effector

logger = logging.getLogger(__name__)

def get_effector(
        effector_type: str|None = None,
        facility: str|None = None,
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True,
    ) -> Effector:
    try:
        return get_effectors(
            effector_type=effector_type,
            facility=facility,
            directory=directory,
            uid=uid,
            active=active
        )[0]
    except Exception as e:
        logger.debug(e)
        raise Exception(e)

def get_effectors(
        effector_type: str|None = None,
        facility: str|None = None,
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[Effector]:
    if uid:
        query = (f"""MATCH (effector:Effector) WHERE effector.uid="{uid}" RETURN effector;""")
    elif effector_type and facility:
        query=(f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid="{facility}" MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid="{effector_type}" MATCH (entry)-[:HAS_EFFECTOR]->(effector:Effector) RETURN DISTINCT effector;""")
    else:
        query=(f"""MATCH (effector:Effector) RETURN effector;""")
    q = db.cypher_query(query,resolve_objects = True)
    effectors: list[Effector]=[]
    if q:
        for row in q[0]:
            logger.debug(row)
            (
                effector,
            ) = row
            effector_dct=effector.__properties__
            try:
                e=Effector.model_validate(effector_dct)
                effectors.append(e)
            except ValidationError as e:
                logger.debug(e)
                raise ValidationError(e)
    return effectors

def create_effector(kwargs)->Effector:
    logger.debug(kwargs)
    node = EffectorNeo4j(
        name_fr=kwargs["name_fr"],
        label_fr=kwargs["label_fr"],
        slug_fr=kwargs["slug_fr"],
        gender=kwargs["gender"],
    ).save()
    effector=EffectorNeo4j.nodes.get(uid=node.uid)
    effector_dct=effector.__properties__
    effector=Effector.model_validate(effector_dct)
    logger.debug(effector)
    return effector