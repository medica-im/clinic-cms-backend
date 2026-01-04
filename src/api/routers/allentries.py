import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends
from api.types.allentry import Entry
from api.auth import authorize_api, role_from_request_jwt
from api.auth import JWT
from api.serializers.allentries import get_all_entries
from api.auth import get_role_from_request_jwt

logger = logging.getLogger(__name__)

router = APIRouter()

def check_cookie_jwt(request: Request):
    if not request.cookies.get('__Secure-authjs.session-token') and not request.cookies.get('authjs.session-token'):
        return
    else:
        return JWT(req=request)


@router.get("/entries")
async def entries(req: Request, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> list[Entry]:
    logger.debug(f"{jwt=}")
    role = await get_role_from_request_jwt(req,jwt)
    logger.debug(f"{role=}")
    return get_all_entries(req, jwt, role)