from fastapi import APIRouter
from api.serializers.effector_type import get_effector_types, get_effector_type
from api.types.effector_type import EffectorType
from pydantic import ValidationError

router = APIRouter()

@router.get("/effector-types")
async def organization_types() -> list[EffectorType]:
    return get_effector_types()

@router.get("/effector-types/{uid}")
async def organization_type(uid: str)->EffectorType:
    return get_effector_type(uid=uid)