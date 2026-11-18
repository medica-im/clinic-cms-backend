import logging
from fastapi import APIRouter, HTTPException, status
from neomodel import adb
from api.types.carehome import CareHome

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/carehomes/{uid}")
async def carehome(uid: str) -> CareHome:
    query = """
    MATCH (c:CareHome {uid: $uid})
    RETURN c
    """
    results, _ = await adb.cypher_query(query, {"uid": uid}, resolve_objects=True)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CareHome {uid} not found",
        )
    node = results[0][0]
    return CareHome(
        uid=node.uid,
        regular_permanent_bed=node.regular_permanent_bed,
        regular_temporary_bed=node.regular_temporary_bed,
        alzheimer_permanent_bed=node.alzheimer_permanent_bed,
        alzheimer_temporary_bed=node.alzheimer_temporary_bed,
        uvpha_permanent_bed=node.uvpha_permanent_bed,
        uhr_permanent_bed=node.uhr_permanent_bed,
        day_care=node.day_care,
        usld_permanent_bed=node.usld_permanent_bed,
    )
