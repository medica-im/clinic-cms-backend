"""POST /api/v2/mail/check-addresses: addresses checked before sending.

For the invitation form: a typo suggestion, a domain that cannot receive
mail, an address already known to be bad (mailer.addresscheck). Warnings
only. Guarded like the invitations it serves. See
tests/api/test_address_checks.py.
"""
from typing import Annotated

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import JWT, authorize_api
from api.utils import get_site_from_request
from facility.models import Organization
from mailer.addresscheck import check

router = APIRouter()


class AddressesToCheck(BaseModel):
    emails: list[str] = Field(max_length=50)


class AddressCheck(BaseModel):
    email: str
    suggestion: str | None = None
    problem: str | None = None


@router.post("/mail/check-addresses")
async def check_addresses(
    body: AddressesToCheck, request: Request, jwt: Annotated[dict, Depends(JWT)],
) -> list[AddressCheck]:
    await authorize_api("invitees_v2", request, jwt)
    site = await get_site_from_request(request)
    organization = await Organization.objects.filter(site=site).afirst()
    return [AddressCheck(**await sync_to_async(check)(email, organization)) for email in body.emails]
