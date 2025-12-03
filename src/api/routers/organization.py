import logging
from fastapi import APIRouter, Request, HTTPException
from api.serializers.organization import get_organizations, get_organization, create_organization
from api.types.organization import Organization as OrganizationPy
from facility.models import Organization
from facility.serializers import OrganizationSerializer
from api.utils import sync_get_site_from_request

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/organization")
def organization(request: Request) -> OrganizationPy:
    logger.debug(request)
    site = sync_get_site_from_request(request)
    try:
        org = Organization.objects.get(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(status_code=404, detail="Organization not found")
    serializer = OrganizationSerializer(org)
    org_dct = serializer.data
    org_validated = OrganizationPy.model_validate(org_dct)
    return org_validated

