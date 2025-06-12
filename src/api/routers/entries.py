from fastapi import APIRouter, status
from api.serializers.entries import get_entries, create_entry
from api.types.entry import EntryPost

router = APIRouter()

@router.get("/entries")
async def entries(effector_type: str|None = None, effector: str|None = None, facility: str|None = None ) -> list[str]:
    return get_entries(effector_type=effector_type, effector=effector, facility=facility)

@router.post("/entries/", status_code=status.HTTP_201_CREATED)
async def post_entry(entry: EntryPost) -> str:
    return create_entry(entry.model_dump())
