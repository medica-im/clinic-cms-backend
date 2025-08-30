import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.types.third_party_payer import ThirdPartyPayer
from directory.models.agraph import ThirdPartyPayer as AsyncThirdPartyPayer
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/third_party_payers/")
async def entries() -> list[ThirdPartyPayer]:
    items = await AsyncThirdPartyPayer.nodes
    return [ThirdPartyPayer.model_validate(item.__properties__) for item in items]