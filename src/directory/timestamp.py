import logging

from neomodel import db

logger = logging.getLogger(__name__)

def update_contact_timestamp(uid):
    logger.warn(f"update_contact_timestamp({uid})")
    query=f"""MATCH (f:Facility) WHERE f.uid="{uid}" SET f.contactUpdatedAt=timestamp() RETURN f;"""
    results, cols = db.cypher_query(query)
    logger.warn(results)
    if results:
        return
    query=f"""MATCH (f:Facility)-[rel:LOCATION]-(e:Effector) WHERE rel.uid="{uid}" SET rel.contactUpdatedAt=timestamp();"""
    results, cols = db.cypher_query(query)