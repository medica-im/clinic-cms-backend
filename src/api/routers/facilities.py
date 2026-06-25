import os
import logging
from typing import Annotated, Union
from fastapi import APIRouter, status, Depends, Request, HTTPException
from api.serializers.facility import async_get_facilities, async_get_facility, create_facility, update_facility, delete_facility
from api.types.facility import Facility, FacilityPost, FacilityPut
from api.auth import authorize_api, verify_user_access, JWT
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.utils import get_site_from_request
from facility.models import Organization
from directory.models.agraph import Facility as AgraphFacility

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/facilities")
async def facilities(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[Facility]:
    site = await get_site_from_request(request)
    raw_role = await get_neo4j_role(jwt, site) or "anonymous"
    role = normalize_neo4j_role(raw_role)
    if role not in ("staff", "administrator", "superuser"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role or higher required"
        )
    if role == "superuser":
        return await async_get_facilities()
    # staff / administrator: return only facilities from this organization
    org = await Organization.objects.aget(site=site)
    if not org.neomodel_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization has no linked Entry"
        )
    entry_uid = org.neomodel_uid.hex
    await verify_user_access(jwt, entry_uid)
    return await async_get_facilities(entry_uid=entry_uid)

@router.get("/facilities/{uid}")
async def facility(uid: str) -> Facility:
    return await async_get_facility(uid=uid)

@router.get("/facilities-slug/{slug}")
async def facility_by_slug(slug: str) -> Facility:
    return await async_get_facility(slug=slug)

@router.post("/facilities/", status_code=status.HTTP_201_CREATED)
async def post_facility(facility: FacilityPost, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    logger.debug(f'${facility=}')
    await authorize_api("facilities_v2", request, jwt)
    return await create_facility(facility, request, jwt)

async def get_facility_users(uid: str):
    """Get owners/creators from Entry nodes linked to this Facility."""
    try:
        facility_node = await AgraphFacility.nodes.get(uid=uid)
    except AgraphFacility.DoesNotExist:
        raise HTTPException(status_code=404, detail="Facility not found")
    users = []
    for entry_node in await facility_node.entries.all():
        users.extend(await entry_node.owner.all() or await entry_node.creator.all())
    return users

@router.put("/facilities/{uid}", status_code=status.HTTP_201_CREATED)
async def put_facility(uid: str, facility: FacilityPut, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> Facility:
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)
    return await update_facility(uid, facility, request)

@router.delete("/facilities/{uid}")
async def delete(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    users = await get_facility_users(uid)
    await authorize_api("facilities_v2", request, jwt, users)
    return await delete_facility(uid)