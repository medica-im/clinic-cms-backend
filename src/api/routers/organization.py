from fastapi import APIRouter, Request, HTTPException
from api.serializers.organization import get_organizations, get_organization, create_organization
from api.types.organization import Organization as OrganizationPy
from facility.models import Organization
from api.utils import get_site_from_request

router = APIRouter()

@router.get("/organization")
async def organization(request: Request) -> OrganizationPy:
    site = await get_site_from_request(request)
    try:
        org = await Organization.objects.aget(site=site)
    except Organization.DoesNotExist:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationPy.model_validate(org.__dict__)

