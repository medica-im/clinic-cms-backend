import logging, os, sys
from typing import Annotated
from fastapi import APIRouter, status, Depends, Request
from api.serializers.effector import get_effector, get_effectors, create_effector, patch_effector
from api.types.effector import Effector, EffectorPost, EffectorPatch
from pydantic import ValidationError
#from api.auth import JWT
from api.auth import authorize_api
from fastapi_nextauth_jwt import NextAuthJWT
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

auth_secret=os.getenv("AUTH_SECRET")
if auth_secret:
    JWT = NextAuthJWT(
        secret=auth_secret,
        csrf_prevention_enabled=False
    )

router = APIRouter()

@router.get('/cookie')
async def get_cookie(request: Request):
    logger.debug(f"{request.cookies.get('__Secure-authjs.session-token')=}")
    logger.info(f"{request.client=}")
    logger.info(f"get cookie {request.headers=}")
    logger.info(f"get cookie {request.cookies=}")
    return request.cookies.get('__Secure-authjs.session-token')

@router.post('/cookie')
async def post_cookie(request: Request, jwt: Annotated[dict, Depends(JWT)]):
    logger.info(f"JWT cookie {request.client=}")
    logger.info(f"JWT cookie {request.headers}")
    logger.info(f"JWT cookie {request.cookies}")
    logger.debug(f"JWT cookie {request.cookies.get('__Secure-authjs.session-token')=}")
    return request.cookies.get('__Secure-authjs.session-token')

@router.get("/effectors")
async def effectors(effector_type: str|None = None, department_of_france: str|None = None, commune: str|None = None, facility: str|None = None ) -> list[Effector]:
    return get_effectors(effector_type=effector_type, department_of_france=department_of_france, commune=commune, facility=facility)

@router.get("/effectors/{uid}")
async def effector(uid: str)->Effector:
    return get_effector(uid=uid)

@router.post("/effectors")
async def post_effector(jwt: Annotated[dict, Depends(JWT)], effector: EffectorPost, request: Request) -> Effector:
    await authorize_api("effectors_v2", request, jwt)
    return await create_effector(effector.model_dump())

@router.patch("/effectors/{uid}")
async def patch_entry(uid: str, effector: EffectorPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("effectors_v2", request, jwt)
    return await patch_effector(uid, effector.model_dump(exclude_unset=True))