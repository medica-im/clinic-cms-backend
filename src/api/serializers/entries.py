import logging
from neomodel import db
from fastapi import HTTPException
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

def entry_if_exists(effector: Effector, effector_type: EffectorType, facility: Facility):
    entry_uids: list[str] = get_entries(
        effector=effector.uid,
        effector_type=effector_type.uid,
        facility=facility.uid
    )
    if not entry_uids:
        return
    active_entries = []
    inactive_entries = []
    for uid in entry_uids:
        entry=Entry.nodes.get(uid=uid)
        if entry.active:
            active_entries.append(entry)
        else:
             inactive_entries.append(entry)
    if len(active_entries) > 1:
        raise HTTPException(status_code=452, detail=f"{len(active_entries)} active Entry objects with same effector, effector_type and facility already exist.")
    if len(active_entries) == 1:
        raise HTTPException(status_code=452, detail="One active Entry object with same effector, effector_type and facility already exists.")
    if len(inactive_entries) > 1:
        raise HTTPException(status_code=452, detail=f"{len(inactive_entries)} inactive Entry objects with same effector, effector_type and facility already exist.")
    if len(inactive_entries) == 1:
        entry = inactive_entries[0]
        entry.active = True
        entry.save()
        return entry

def connect_orgs(entry:Entry, organizations: list[str]|None):
    if organizations:
        for org_uid in organizations:
            try:
                org = Organization.nodes.get(uid=org_uid)
                entry.organizations.connect(org)
            except Exception as e:
                logger.error(e)
                raise Exception(e)

def create_entry(dir_name, kwargs)-> str:
    organizations = kwargs["organizations"]
    neo4j_directory=Neo4jDirectory.nodes.get(name=dir_name)
    effector=Effector.nodes.get(uid=kwargs["effector"])
    effector_type=EffectorType.nodes.get(uid=kwargs["effector_type"])
    facility=Facility.nodes.get(uid=kwargs["facility"])
    entry=entry_if_exists(effector,effector_type,facility)
    if not entry:
        entry=Entry()
        entry.save()
        entry.effector.connect(effector)
        entry.effector_type.connect(effector_type)
        entry.facility.connect(facility)
    connect_orgs(entry, organizations)
    neo4j_directory.entries.connect(entry)
    return str(entry.uid)