import logging
from neomodel import adb
from fastapi import HTTPException
logger = logging.getLogger(__name__)

async def slug_find_entry(commune: str, effector: str, type: str)->str:
    query=(
        f"""MATCH (e:Entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c:Commune), (e)-[:HAS_EFFECTOR]->(effector:Effector), (e)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
        WHERE c.slug_fr="{commune}" AND effector.slug_fr="{effector}" AND et.slug_fr="{type}" RETURN e.uid;"""
    )
    results, cols = await adb.cypher_query(query)
    logger.debug(f"{results=}\n{cols=}")
    if not results:
        raise HTTPException(status_code=404, detail="Entry not found")