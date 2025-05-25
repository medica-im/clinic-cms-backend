from fastapi import APIRouter, status
from api.serializers.geography import get_communes, get_commune
from api.types.geography import Commune

router = APIRouter()

@router.get("/communes")
async def communes() -> list[Commune]:
    return get_communes()

@router.get("/communes/{uid}")
async def organization(uid: str) -> Commune:
    return get_commune(uid=uid)