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
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    nodes: list[EffectorTypePy]=[]
    for row in results:
        org=EffectorType.inflate(row[cols.index('n')])
        logger.debug(org.__dict__)
        logger.debug(org.__properties__)
        logger.debug(org)
        try:
            org_dct=org.__properties__
            org=EffectorTypePy.model_validate(org_dct)
            logger.debug(org)
            nodes.append(org)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes