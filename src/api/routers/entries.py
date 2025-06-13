import logging
from fastapi import APIRouter, status, Request
from api.serializers.entries import get_entries, create_entry
from api.types.entry import EntryPost

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/entries")
async def entries(effector_type: str|None = None, effector: str|None = None, facility: str|None = None ) -> list[str]:
    return get_entries(effector_type=effector_type, effector=effector, facility=facility)

@router.post("/entries/", status_code=status.HTTP_201_CREATED)
async def post_entry(entry: EntryPost, request: Request) -> str:
    logger.debug(request)
    logger.debug(f"{request.url=}")
    if request.client:
        try:
            client_host = request.client.host
            logger.debug(client_host)
        except:
            pass
    return create_entry(entry.model_dump())
