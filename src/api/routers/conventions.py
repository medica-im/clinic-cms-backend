import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.types.convention import Convention
from directory.models.agraph import Convention as AsyncConvention
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/conventions/")
async def entries() -> list[Convention]:
    items = await AsyncConvention.nodes
    return [Convention.model_validate(item.__properties__) for item in items]