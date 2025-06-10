import logging
from fastapi import APIRouter, status
from api.serializers.effector import get_effector, get_effectors, create_effector
from api.types.effector import Effector
from pydantic import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/effectors")
async def organization_types(effector_type: str|None = None, facility: str|None = None ) -> list[Effector]:
    return get_effectors(effector_type=effector_type, facility=facility)

@router.get("/effectors/{uid}")
async def organization_type(uid: str)->Effector:
    return get_effector(uid=uid)

@router.post("/effectors/", status_code=status.HTTP_201_CREATED)
async def post_effector(effector: Effector) -> Effector:
    logger.debug(effector.model_dump())
    return create_effector(effector.model_dump())
