import logging
from fastapi import APIRouter, status, HTTPException
from api.serializers.organization import get_organizations, get_organization, create_organization
from fastapi.encoders import jsonable_encoder
from addressbook.models import PhoneNumber
from api.types.phones import Phone

logger = logging.getLogger(__name__)

router = APIRouter()

@router.put("/phones/{item_id}", response_model=Phone)
async def update_item(item_id: str, item: Phone):
    logger.debug(item)
    update_item_encoded = jsonable_encoder(item)
    logger.debug(update_item_encoded)
    try:
        phone_number = PhoneNumber.objects.get(id=item_id)
        logger.debug(phone_number)
    except PhoneNumber.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"PhoneNumber not found")
    logger.debug(update_item_encoded)
    return update_item_encoded
