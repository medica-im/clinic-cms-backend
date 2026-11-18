"""An organization's invitation settings.

Administrators and higher read them: the list's resend mode preselects with
them. Superusers change them. The role comes from this site's graph alone,
as for the email templates (api.email_access).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT
from api.neo4j_auth import get_neo4j_role
from api.types.invitation_settings import InvitationSettings
from api.utils import get_site_from_request
from facility.models import Organization
from mailer.access import may_view

logger = logging.getLogger(__name__)

router = APIRouter()


async def _organization(request: Request, jwt: dict, *, change: bool = False) -> Organization:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    allowed = role == "superuser" if change else may_view(role)
    if not allowed:
        logger.warning("refused %s %s for role=%r", request.method, request.url.path, role)
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        return await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No organization for this site")


def _out(organization: Organization) -> InvitationSettings:
    return InvitationSettings(resendAfterDays=organization.invitation_resend_after_days)


@router.get("/invitation-settings", response_model=InvitationSettings)
async def get_invitation_settings(request: Request, jwt: Annotated[dict, Depends(JWT)]):
    return _out(await _organization(request, jwt))


@router.patch("/invitation-settings", response_model=InvitationSettings)
async def update_invitation_settings(
    settings: InvitationSettings,
    request: Request,
    jwt: Annotated[dict, Depends(JWT)],
):
    organization = await _organization(request, jwt, change=True)
    organization.invitation_resend_after_days = settings.resendAfterDays
    await organization.asave(update_fields=["invitation_resend_after_days"])
    return _out(organization)
