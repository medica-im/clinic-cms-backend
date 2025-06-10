from fastapi import APIRouter
from api.serializers.effector import get_effector, get_effectors
from api.types.effector import Effector
from pydantic import ValidationError

router = APIRouter()

@router.get("/effectors")
async def organization_types(effector_type: str|None = None, facility: str|None = None ) -> list[Effector]:
    return get_effectors(effector_type=effector_type, facility=facility)

@router.get("/effectors/{uid}")
async def organization_type(uid: str)->Effector:
    return get_effector(uid=uid)