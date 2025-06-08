import logging
import json
from typing import Union
from pydantic import ValidationError
from neomodel import db
from directory.models import (
    Directory,
    EffectorType,
)
from api.types.effector_type import EffectorType as EffectorTypePy

logger = logging.getLogger(__name__)

def get_effector_type(
    directory: Directory|None = None,
    uid: str|None = None,
    active: bool = True) -> EffectorTypePy:
    return get_effector_types(
        directory=directory,
        uid=uid,
        active=active
    )[0]

def get_effector_types(
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[EffectorTypePy]:
    label: str = "EffectorType"
    if uid:
        query=f"""MATCH (et:{label}) OPTIONAL MATCH (n:Need)<-[:MANAGES]-(et)-[:MANAGES]->(s:Situation), (et)-[:IS_A]->(et2:EffectorType)
        WHERE et.uid="{uid}"
        RETURN DISTINCT et,collect(s),collect(n),et2;"""
    else:
        query=f"""MATCH (et:{label}) OPTIONAL MATCH (n:Need)<-[:MANAGES]-(et)-[:MANAGES]->(s:Situation), (et)-[:IS_A]->(et2:EffectorType)
        RETURN DISTINCT et,collect(s),collect(n),et2;"""
    q = db.cypher_query(query, resolve_objects = True)
    nodes: list[EffectorTypePy]=[]
    for row in q[0]:
        logger.debug(f"{row=}")
        (
            effector_type,
            situations,
            needs,
            related_effector_type,
        ) = row
        logger.debug(effector_type)
        logger.debug(situations)
        logger.debug(needs)
        ret_dct=None
        if related_effector_type:
            ret_dct=related_effector_type.__dict__
        logger.debug(ret_dct)
        try:
            et_dct=effector_type.__properties__
            et_dct["effector_type"]=ret_dct
            et_dct["situation"]=None
            et_dct["need"]=None
            et=EffectorTypePy.model_validate(et_dct)
            logger.debug(et)
            nodes.append(et)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes