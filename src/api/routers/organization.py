import logging
from fastapi import APIRouter, Request, HTTPException
from api.serializers.organization import (
    get_organizations,
    get_organization,
    create_organization,
    async_get_django_organization,
)
from api.types.organization import Organization as OrganizationPy
from facility.models import Organization
from api.utils import get_site_from_request

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/organization")
async def organization(request: Request) -> OrganizationPy:
    logger.debug(f"{request.headers=}")
    logger.debug(f"{request.client=}")
    site = await get_site_from_request(request)
    try:
        org = await Organization.objects.aget(site=site, active=True)
    except Organization.DoesNotExist:
        raise HTTPException(status_code=404, detail="Organization not found")
    org_dct = await async_get_django_organization(org)
    org_validated = OrganizationPy.model_validate(org_dct)
    return org_validated

