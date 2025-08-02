import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from addressbook.models import PhoneNumber
from api.types.phones import Phone
from api.auth import JWT
from api.auth import authorize_api

logger = logging.getLogger(__name__)

router = APIRouter()

@router.put("/phones/{item_id}", response_model=Phone)
async def update_item(item_id: str, item: Phone, request: Request, jwt: Annotated[dict, Depends(JWT)]):
    await authorize_api("phones_v2", request, jwt)
    logger.debug(item)
    update_item_encoded = jsonable_encoder(item)
    logger.debug(update_item_encoded)
    try:
        phone_number = await PhoneNumber.objects.aget(id=item_id)
        logger.debug(phone_number)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")
    logger.debug(update_item_encoded)
    phone_number.type=update_item_encoded['type']
    phone_number.phone=update_item_encoded['phone']
    await phone_number.asave()
    return update_item_encoded
