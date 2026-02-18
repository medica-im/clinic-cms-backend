import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends
from api.types.allentry import Entry
from api.auth import JWT
from api.serializers.allentries import get_all_entries
from api.auth import get_role_from_jwt, check_cookie_jwt, authorize_api

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/entries")
async def entries(request: Request, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> list[Entry]:
    await authorize_api("entries_v2", request, jwt)
    roles = await get_role_from_jwt(jwt)
    return await get_all_entries(request, jwt, roles)