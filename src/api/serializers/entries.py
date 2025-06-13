import logging
from neomodel import db
from directory.models import (
    Directory,
    Facility,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance,
    Effector,
    EffectorType,
    Entry,
    Neo4jDirectory,
)

logger = logging.getLogger(__name__)

def get_entries(
        effector_type: str|None = None,
        facility: str|None = None,
        effector: str|None = None,
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[str]:
    if effector_type and facility and effector:
        query=(
            f"""MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector) WHERE effector.uid="{effector}" MATCH (entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid="{facility}, (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid="{effector_type}" RETURN DISTINCT entry.uid;"""
        )
    elif effector_type and facility:
        query=(
            f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid="{facility}" MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid="{effector_type}" RETURN DISTINCT entry.uid;""")
    q = db.cypher_query(query,resolve_objects = True)
    uids=[]
    if q:
        results = q[0]
        uids = [
            _uid
            for xs in results
            for _uid in xs
            
        ]
        logger.debug(uids)
    return uids

def create_entry(dir_name, kwargs)-> str:
    neo4j_directory=Neo4jDirectory.nodes.get(name=dir_name)
    entry=Entry()
    entry.save()
    effector=Effector.nodes.get(uid=kwargs["effector"])
    effector_type=EffectorType.nodes.get(uid=kwargs["effector_type"])
    facility=Facility.nodes.get(uid=kwargs["facility"])
    entry.effector.connect(effector)
    entry.effector_type.connect(effector_type)
    entry.facility.connect(facility)
    neo4j_directory.entries.connect(entry)
    return str(entry.uid)
    