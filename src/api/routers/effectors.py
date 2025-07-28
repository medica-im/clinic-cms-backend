import logging
from typing import Annotated
from fastapi import APIRouter, status, Depends
from api.serializers.effector import get_effector, get_effectors, create_effector
from api.types.effector import Effector, EffectorPost
from pydantic import ValidationError
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/effectors")
async def effectors(effector_type: str|None = None, department_of_france: str|None = None, commune: str|None = None, facility: str|None = None ) -> list[Effector]:
    return get_effectors(effector_type=effector_type, department_of_france=department_of_france, commune=commune, facility=facility)

@router.get("/effectors/{uid}")
async def effector(uid: str)->Effector:
    return get_effector(uid=uid)

@router.post("/effectors/", status_code=status.HTTP_201_CREATED)
async def post_effector(effector: EffectorPost, jwt: Annotated[dict, Depends(JWT)]) -> Effector:
    logger.debug(effector.model_dump())
    return create_effector(effector.model_dump())
