import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.serializers.entries import get_entries, create_entry
from api.types.entry import EntryPost
from api.utils import get_directory_from_hostname
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/entries")
async def entries(effector_type: str|None = None, effector: str|None = None, facility: str|None = None ) -> list[str]:
    return get_entries(effector_type=effector_type, effector=effector, facility=facility)

@router.post("/entries/", status_code=status.HTTP_201_CREATED)
async def post_entry(entry: EntryPost, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> str:
    await authorize_api("entries_v2", request, jwt)
    directory = await get_directory_from_hostname(request.url.hostname)
    return create_entry(directory.name, entry.model_dump())
