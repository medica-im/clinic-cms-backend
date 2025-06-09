from fastapi import APIRouter, status
from api.serializers.entries import get_entries
from api.types.geography import Commune

router = APIRouter()

@router.get("/entries")
async def communes(effector_type: str|None = None, effector: str|None = None, facility: str|None = None ) -> list[str]:
    return get_entries(effector_type=effector_type, effector=effector, facility=facility)
