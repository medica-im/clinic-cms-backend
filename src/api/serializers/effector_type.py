import logging
import json
from typing import Union
from pydantic import ValidationError
from neomodel import db, adb
from directory.models import (
    Directory,
    EffectorType,
    HCW,
)
from directory.models.graph import RPPS
from directory.models.agraph import (
    EffectorType as AsyncEffectorType,
    HCW as AsyncHCW,
    RPPS as AsyncRPPS,
)
from api.types.effector_type import (
    EffectorType as EffectorTypePy,
    EffectorTypePost,
    EffectorTypePatch,
)

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
    if uid:
        query=f"""MATCH (et:EffectorType) WHERE et.uid="{uid}" OPTIONAL MATCH (et)-[:MANAGES]->(s:Situation) OPTIONAL MATCH (et)-[:MANAGES]->(n:Need) OPTIONAL MATCH (et)-[:IS_A]->(et2:EffectorType) OPTIONAL MATCH (et)-[:HAS_TAG_CATEGORY]->(tc:TagCategory) RETURN DISTINCT et,collect(DISTINCT s),collect(DISTINCT n),et2,collect(DISTINCT tc);"""
    else:
        query=f"""MATCH (et:EffectorType) OPTIONAL MATCH (et)-[:MANAGES]->(s:Situation) OPTIONAL MATCH (et)-[:MANAGES]->(n:Need) OPTIONAL MATCH (et)-[:IS_A]->(et2:EffectorType) OPTIONAL MATCH (et)-[:HAS_TAG_CATEGORY]->(tc:TagCategory) RETURN DISTINCT et,collect(DISTINCT s),collect(DISTINCT n),et2,collect(DISTINCT tc);"""
    q = db.cypher_query(query, resolve_objects = True)
    nodes: list[EffectorTypePy]=[]
    for row in q[0]:
        logger.debug(f"{row=}")
        (
            effector_type,
            situations,
            needs,
            related_effector_type,
            tag_category
        ) = row
        logger.debug(f"{effector_type=}")
        logger.debug(f"{situations[:1]=}")
        logger.debug(f"{needs[:1]=}")
        logger.debug(f"{tag_category=}")
        ret_dct=None
        if related_effector_type:
            ret_dct=related_effector_type.__dict__
        logger.debug(f"{ret_dct=}")
        try:
            et_dct=effector_type.__properties__
            et_dct["effector_type"]=None
            et_dct["effector_type_uid"] = related_effector_type.uid if related_effector_type else None
            et_dct["effector_type_label_fr"] = related_effector_type.label_fr if related_effector_type else None
            et_dct["isHCW"] = isinstance(effector_type, HCW)
            et_dct["isRPPS"] = isinstance(effector_type, RPPS)
            et_dct["situation"]=None
            et_dct["need"]=None
            et=EffectorTypePy.model_validate(et_dct)
            logger.debug(et)
            nodes.append(et)
        except ValidationError as e:
            logger.debug(e)
            raise ValidationError(e)
    return nodes


def _get_node_class(isHCW: bool, isRPPS: bool):
    if isRPPS:
        return AsyncRPPS
    if isHCW:
        return AsyncHCW
    return AsyncEffectorType


def _node_properties(data: dict) -> dict:
    """Extract non-node-property fields from the input dict."""
    exclude = {"isHCW", "isRPPS", "effector_type_uid"}
    return {k: v for k, v in data.items() if k not in exclude}


async def _connect_effector_type_rel(node, effector_type_uid: str|None):
    """Connect or replace the IS_A relationship to a parent EffectorType."""
    if effector_type_uid is None:
        return
    await adb.cypher_query(
        "MATCH (n:EffectorType {uid: $uid})-[r:IS_A]->() DELETE r",
        {"uid": node.uid},
    )
    await adb.cypher_query(
        "MATCH (n:EffectorType {uid: $child_uid}), (p:EffectorType {uid: $parent_uid}) "
        "MERGE (n)-[:IS_A]->(p)",
        {"child_uid": node.uid, "parent_uid": effector_type_uid},
    )


async def create_effector_type(data: EffectorTypePost) -> EffectorTypePy:
    node_cls = _get_node_class(data.isHCW, data.isRPPS)
    props = _node_properties(data.model_dump(exclude_unset=False))
    node = await node_cls(**props).save()
    await _connect_effector_type_rel(node, data.effector_type_uid)
    saved = await node_cls.nodes.get(uid=node.uid)
    et_dct = saved.__properties__
    et_dct["effector_type"] = None
    et_dct["situation"] = None
    et_dct["need"] = None
    et_dct["isHCW"] = data.isHCW
    et_dct["isRPPS"] = data.isRPPS
    if data.effector_type_uid:
        parent = await AsyncEffectorType.nodes.get(uid=data.effector_type_uid)
        et_dct["effector_type_uid"] = parent.uid
        et_dct["effector_type_label_fr"] = parent.label_fr
    else:
        et_dct["effector_type_uid"] = None
        et_dct["effector_type_label_fr"] = None
    return EffectorTypePy.model_validate(et_dct)


async def delete_effector_type(uid: str):
    """Delete an EffectorType node."""
    node = await AsyncEffectorType.nodes.get(uid=uid)
    await node.delete()


async def disconnect_effector_type_rel(uid: str):
    """Disconnect all IS_A relationships from the given EffectorType node."""
    node = await AsyncEffectorType.nodes.get(uid=uid)
    existing = await node.effector_type.all()
    for old in existing:
        await node.effector_type.disconnect(old)


async def _sync_labels(uid: str, isHCW: bool | None, isRPPS: bool | None):
    """Add or remove HCW/RPPS labels on the node via Cypher."""
    if isHCW is None and isRPPS is None:
        return
    if isRPPS:
        # RPPS implies HCW
        await adb.cypher_query(
            "MATCH (n:EffectorType {uid: $uid}) SET n:HCW:RPPS",
            {"uid": uid},
        )
    elif isHCW:
        await adb.cypher_query(
            "MATCH (n:EffectorType {uid: $uid}) REMOVE n:RPPS SET n:HCW",
            {"uid": uid},
        )
    else:
        # Plain EffectorType — remove both
        await adb.cypher_query(
            "MATCH (n:EffectorType {uid: $uid}) REMOVE n:HCW:RPPS",
            {"uid": uid},
        )


async def update_effector_type(uid: str, data: EffectorTypePatch) -> EffectorTypePy:
    changed = data.model_dump(exclude_unset=True)
    isHCW = changed.pop("isHCW", None)
    isRPPS = changed.pop("isRPPS", None)
    effector_type_uid = changed.pop("effector_type_uid", None)
    # Always fetch with the base class — the node may not have HCW/RPPS labels yet
    node = await AsyncEffectorType.nodes.get(uid=uid)
    for attr, value in changed.items():
        setattr(node, attr, value)
    await node.save()
    await _sync_labels(uid, isHCW, isRPPS)
    await _connect_effector_type_rel(node, effector_type_uid)
    et_dct = node.__properties__
    et_dct["effector_type"] = None
    et_dct["situation"] = None
    et_dct["need"] = None
    et_dct["isHCW"] = bool(isHCW)
    et_dct["isRPPS"] = bool(isRPPS)
    if effector_type_uid:
        parent = await AsyncEffectorType.nodes.get(uid=effector_type_uid)
        et_dct["effector_type_uid"] = parent.uid
        et_dct["effector_type_label_fr"] = parent.label_fr
    else:
        et_dct["effector_type_uid"] = None
        et_dct["effector_type_label_fr"] = None
    return EffectorTypePy.model_validate(et_dct)