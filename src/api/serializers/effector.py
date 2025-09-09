import logging
from django.utils.text import slugify
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
from directory.models.agraph import Effector as EffectorNeo4j
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
        department_of_france: str|None = None,
        commune: str|None = None,
        facility: str|None = None,
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[Effector]:
    filter: list = []
    if effector_type:
        filter.append(f'et.uid="{effector_type}"')
    if facility:
        filter.append(f'f.uid="{facility}"')
    elif commune:
        filter.append(f'commune.uid="{commune}"')
    elif department_of_france:
        filter.append(f'dof.code="{department_of_france}"')
    if uid:
        query = (f"""MATCH (effector:Effector) WHERE effector.uid="{uid}" RETURN effector;""")
    elif not filter:
        query=(f"""MATCH (effector:Effector) RETURN effector;""")
    else:
        query=(f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY
]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY
]->(dof:DepartmentOfFrance), (effector:Effector)<-[:HAS_EFFECTOR]-(entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE {" AND ".join(filter)} RETURN DISTINCT effector;""")
    logger.debug(f"{query=}")
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

async def create_effector(kwargs)->Effector:
    logger.debug(kwargs)
    node = await EffectorNeo4j(
        name_fr=kwargs["name_fr"],
        label_fr=kwargs["label_fr"] or kwargs["name_fr"],
        slug_fr=kwargs["slug_fr"] or slugify(kwargs["name_fr"]),
        gender=kwargs["gender"],
    ).save()
    effector= await EffectorNeo4j.nodes.get(uid=node.uid)
    effector_dct=effector.__properties__
    effector=Effector.model_validate(effector_dct)
    logger.debug(effector)
    return effector

async def patch_effector(uid, kwargs)->Effector:
    logger.debug(kwargs)
    node = await EffectorNeo4j.nodes.get(uid=uid)
    logger.debug(kwargs.keys())
    logger.debug(f'{kwargs["rpps"]=} {type(kwargs["rpps"])=}')
    logger.debug("rpps" in kwargs.keys())
    if "rpps" in kwargs.keys():
        node.rpps=kwargs["rpps"]
    await node.save()
    effector_dct=node.__properties__
    effector=Effector.model_validate(effector_dct)
    logger.debug(effector)
    return effector