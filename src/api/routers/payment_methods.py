import logging
from typing import Annotated
from fastapi import APIRouter, status, Request, Depends
from api.types.payment_method import PaymentMethod
from directory.models.agraph import PaymentMethod as AsyncPaymentMethod
from api.auth import authorize_api
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/payment_methods/")
async def entries() -> list[PaymentMethod]:
    methods = await AsyncPaymentMethod.nodes
    return [PaymentMethod.model_validate(method.__properties__) for method in methods]
