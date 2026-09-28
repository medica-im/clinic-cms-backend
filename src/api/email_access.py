"""The gate of the email template and email image endpoints.

Not authorize_api: the rule is not a role x method table but "administrators
and higher see, the organization's chosen role changes" (mailer.access), and
the role comes from this site's graph alone, like api.routers.admin_entries --
authorize_api's legacy fallback would make a Django superuser an
administrator of every site.
"""

import logging
from dataclasses import dataclass

from django.contrib.sites.models import Site
from fastapi import HTTPException, Request, status

from api.neo4j_auth import get_neo4j_role
from api.utils import get_site_from_request
from facility.models import Organization
from mailer.access import may_edit, may_view

logger = logging.getLogger(__name__)


@dataclass
class EmailAccess:
    site: Site
    organization: Organization
    role: str
    can_edit: bool


async def email_access(request: Request, jwt: dict, *, edit: bool = False) -> EmailAccess:
    """The caller's standing, or 403. With edit=True, 403 unless they may
    change the organization's emails. The role is checked before the
    organization is looked up, so a refused caller learns nothing about it."""
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if not may_view(role):
        logger.warning("refused %s %s for role=%r", request.method, request.url.path, role)
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        organization = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No organization for this site")
    can_edit = may_edit(role, organization)
    if edit and not can_edit:
        logger.warning("refused %s %s: role=%r may not edit", request.method, request.url.path, role)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "not_editor"})
    return EmailAccess(site=site, organization=organization, role=role, can_edit=can_edit)
