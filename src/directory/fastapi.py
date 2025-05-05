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
        uid = None,
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
            org_json=json.dumps(org.__properties__) 
            _organizations.append(org_json)
    except:
        pass
    logger.debug(_organizations)
    return json.dumps(_organizations)