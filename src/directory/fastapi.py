from neomodel import db
from directory.models import (
    Directory,
    Organization,
)

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
            _organizations.append(
                Organization.inflate(row[cols.index('n')])
            )
    except:
        pass
    return _organizations
