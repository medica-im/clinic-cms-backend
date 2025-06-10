from fastapi import APIRouter
from src.api.serializers.effector import get_effector, get_effectors
from api.types.effector import Effector
from pydantic import ValidationError

router = APIRouter()

@router.get("/effectors")
async def organization_types() -> list[Effector]:
    return get_effectors()

@router.get("/effectors/{uid}")
async def organization_type(uid: str)->Effector:
    return get_effector(uid=uid)