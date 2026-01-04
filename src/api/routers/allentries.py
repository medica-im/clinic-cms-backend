import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends
from api.types.allentry import Entry
from api.auth import authorize_api, role_from_request_jwt
from api.auth import JWT
from api.serializers.allentries import get_all_entries

logger = logging.getLogger(__name__)

router = APIRouter()

def check_cookie_jwt(request: Request):
    if not request.cookies.get('__Secure-authjs.session-token') or not request.cookies.get('authjs.session-token'):
        return "anonymous"
    else:
        return JWT(req=request)


@router.get("/entries")
def entries(req: Request, jwt: Annotated[dict, Depends(check_cookie_jwt)]) -> list[Entry]:
    logger.debug(jwt)
    return get_all_entries(req, jwt)