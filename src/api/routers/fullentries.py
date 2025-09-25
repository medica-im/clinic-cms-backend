import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.serializers.fullentry import get_fullentry
from api.types.fullentry import FullEntry
from api.utils import get_directory_from_hostname
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/fullentries/{uid}")
async def get(uid: str) -> FullEntry:
    return get_fullentry(uid)
