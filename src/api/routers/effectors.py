import logging, os, sys
from typing import Annotated
from fastapi import APIRouter, status, Depends, Request, HTTPException
from api.serializers.effector import get_effector, get_effectors, create_effector, update_effector
from directory.models.agraph import Effector as AgraphEffector
from api.routers.utils import get_directory_from_hostname
from api.types.effector import Effector, EffectorPost, EffectorPatch
from pydantic import ValidationError
from api.auth import JWT, authorize_api
from fastapi_nextauth_jwt import NextAuthJWT
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

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
async def effectors(effector_type: str|None = None, department_of_france: str|None = None, commune: str|None = None, facility: str|None = None, directory: str|None = None, owner: str|None = None) -> list[Effector]:
    return get_effectors(effector_type=effector_type, department_of_france=department_of_france, commune=commune, facility=facility, directory=directory, owner=owner)

@router.get("/effectors/{uid}")
async def effector(uid: str)->Effector:
    return get_effector(uid=uid)

@router.post("/effectors")
async def post_effector(jwt: Annotated[dict, Depends(JWT)], effector: EffectorPost, request: Request) -> Effector:
    await authorize_api("effectors_v2", request, jwt)
    directory = await get_directory_from_hostname(request.url.hostname)
    return await create_effector(effector, directory.name, jwt)

@router.patch("/effectors/{uid}")
async def patch_effector(uid: str, effector: EffectorPatch, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    try:
        effector_node = await AgraphEffector.nodes.get(uid=uid)
    except AgraphEffector.DoesNotExist:
        raise HTTPException(status_code=404, detail="Effector not found")
    users = await effector_node.owner.all() or await effector_node.creator.all()
    await authorize_api("effectors_v2", request, jwt, users)
    return await update_effector(uid, effector.model_dump(exclude_unset=True), request)