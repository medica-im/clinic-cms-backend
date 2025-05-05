import logging
import json
from neomodel import db
from directory.models import (
    Directory,
    Organization,
)

logger = logging.getLogger(__name__)

def get_organizations(
        directory: Directory|None = None,
        uid: str|None = None,
        label: str = "Organization",
        active: bool = True,
    ):
    if uid:
        query=f"""MATCH (n:{label})
        WHERE n.uid="{uid}"
        RETURN n;"""
    else:
        query=f"""MATCH (n:{label})
        RETURN n;"""
    results, cols = db.cypher_query(query)
    _organizations=[]
    try:
        for row in results:
            org=Organization.inflate(row[cols.index('n')])
            org=org.__properties__ 
            _organizations.append(org)
    except:
        pass
    logger.debug(_organizations)
    return _organizations