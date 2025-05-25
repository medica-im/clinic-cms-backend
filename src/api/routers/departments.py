from fastapi import APIRouter, status
from api.serializers.geography import get_departments, get_department
from api.types.geography import Commune, DepartmentOfFrance

router = APIRouter()

@router.get("/departments")
async def read_departments() -> list[DepartmentOfFrance]:
    return get_departments()

@router.get("/departments/{uid}")
async def commune(uid: str) -> DepartmentOfFrance:
    return get_department(uid=uid)