import logging
import uuid

from neomodel import db

logger = logging.getLogger(__name__)

def update_contact_timestamp(uid: uuid.UUID):
    if not isinstance(uid, uuid.UUID):
        try:
            uid=uuid.UUID(uid)
        except ValueError:
            logger.error(f"{uid} is not a valid uuid")
            return
    # matching a node requires hex string representation of uuid4 with no dash
    query=f"""MATCH (f:Facility) WHERE f.uid="{uid.hex}" SET f.contactUpdatedAt=timestamp() RETURN f;"""
    results, _cols = db.cypher_query(query)
    if results:
        return
    # matching LOCATION relationship requires the dashed string representation
    # of uuid4
    # old graph structure
    query=(
        f"""
        MATCH (f:Facility)-[rel:LOCATION]-(e:Effector)
        WHERE rel.uid="{uid}"
        SET rel.contactUpdatedAt=timestamp();
    """
    )
    results, _cols = db.cypher_query(query)
    if results:
        return
    # new graph structure
    query=(
        f"""
        MATCH (entry:Entry)
        WHERE entry.uid="{uid}"
        SET entry.contactUpdatedAt=timestamp();
        """
    )
    results, _cols = db.cypher_query(query)