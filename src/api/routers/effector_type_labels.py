import logging

from django.core.cache import cache
from fastapi import APIRouter, Request

from api.serializers.effector_type_labels import get_effector_type_labels
from api.types.effector_type_label import EffectorTypeLabels
from api.utils import (
    DEFAULT_TTL,
    generate_cache_key,
    get_site_from_request,
    get_ttl,
    resolve_ttl,
    set_timestamp,
    strip_slash,
)
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()

API_VERSION = "v2"
TTL = DEFAULT_TTL


@router.get("/effector-type-labels")
async def effector_type_labels(request: Request) -> EffectorTypeLabels:
    """Effector-type labels for the requesting site's language.

    The v2 home of /api/v1/directory/effector_type_labels/, which this replaces
    rather than supplements: the body is identical, so the frontend moves by
    changing the URL alone. Kept bare of an envelope for that reason.

    The language is the requesting site's, resolved through its Directory's
    Organization — this is a per-site response, and the cache key carries the
    domain to match.
    """
    cache_key = await generate_cache_key(API_VERSION, request)
    data = cache.get(cache_key)
    if data is not None:
        logger.debug(f"*** Using cache with key {cache_key} ***")
        # Cached as a plain dict: the response model revalidates it on the way
        # out, so a stale entry whose shape no longer matches fails here rather
        # than reaching the frontend.
        return EffectorTypeLabels(data)

    logger.debug(f"cache for key '{cache_key}' is *** EMPTY ***")
    site = await get_site_from_request(request)
    # The Organization is fetched against the Site rather than walked to from
    # the Directory: `directory.site.organization` is a lazy reverse accessor,
    # and touching it here raises SynchronousOnlyOperation. Same approach as
    # the sibling /organization-role-labels endpoint.
    organization = await Organization.objects.select_related("site").aget(site=site)
    labels = await get_effector_type_labels(organization.language)

    timeout = resolve_ttl(await get_ttl(API_VERSION, request), TTL)
    # model_dump() rather than the model itself: the cache backend has to
    # serialise this, and a pydantic instance is not JSON.
    cache.set(cache_key, labels.model_dump(), timeout=timeout)

    path = strip_slash(request.scope["route"].path)
    endpoint = "%s:%s" % (API_VERSION, path)
    site = await get_site_from_request(request)
    await set_timestamp(endpoint, site)

    return labels
