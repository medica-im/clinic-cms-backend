import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, HTTPException
from api.types.directory import AvailableDirectory
from api.serializers.directories import get_available_directories
from api.utils import get_site_from_request
from api.neo4j_auth import get_neo4j_role
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/directories/available")
async def available_directories(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[AvailableDirectory]:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in ("administrator", "superuser"):
        raise HTTPException(status_code=403, detail="Only administrators and superusers can list directories")
    return await get_available_directories(request)
