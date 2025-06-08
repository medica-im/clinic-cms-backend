from fastapi import APIRouter
from api.serializers.effector_type import get_effector_types, get_effector_type
from api.types.effector_type import EffectorType
from pydantic import ValidationError

router = APIRouter()

@router.get("/organization-types")
async def organization_types() -> list[EffectorType]:
    return get_effector_types()

@router.get("/organization-types/{organization_type_uid}")
async def organization_type(organization_type_uid: str)->EffectorType:
    return get_effector_type(uid=organization_type_uid)