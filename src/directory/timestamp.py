import logging
import uuid

from neomodel import db

logger = logging.getLogger(__name__)

def update_contact_timestamp(uid: uuid.UUID):
    # matching a node requires hex string representation of uuid4 with no dash
    query=f"""MATCH (f:Facility) WHERE f.uid="{uid.hex}" SET f.contactUpdatedAt=timestamp() RETURN f;"""
    results, cols = db.cypher_query(query)
    if results:
        return
    # matching LOCATION relationship requires the dashed string representation
    # of uuid4
    query=f"""MATCH (f:Facility)-[rel:LOCATION]-(e:Effector) WHERE rel.uid="{uid}" SET rel.contactUpdatedAt=timestamp();"""
    results, cols = db.cypher_query(query)