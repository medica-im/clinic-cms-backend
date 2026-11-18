"""Delivery events from the mail service: POST /api/v2/mail/events/{provider}.

Public, and deliberately host-independent: it is reached at each server's own
hostname (dev.medica.im, production.medica.im...), none of which is a Site,
so nothing is looked up from the Host header and no login is involved. Trust
comes from the provider's signature alone. See
tests/api/test_mail_events_webhook.py.

Answers 200 to anything signed, even an event it cannot place: the service
would otherwise retry it for hours.
"""
import logging

from asgiref.sync import sync_to_async
from fastapi import APIRouter, HTTPException, Request, status

from mailer.delivery import apply_event
from mailer.providers import provider_named

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/mail/events/{provider_name}")
async def mail_events(provider_name: str, request: Request) -> dict:
    provider = provider_named(provider_name)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not JSON")
    if not isinstance(payload, dict) or not await sync_to_async(provider.verify_webhook)(payload):
        logger.warning(f"Refused an unsigned or forged {provider_name} event")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    event = provider.parse_event(payload)
    if event is not None:
        await sync_to_async(apply_event)(event)
    return {"ok": True}
