import logging
from typing import Annotated

from asgiref.sync import sync_to_async
from django.core.cache import cache
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import JWT, authorize_api
from api.serializers.effector_type_labels import (
    effector_type_exists,
    get_effector_type_labels,
    get_type_labels,
    set_type_labels,
)
from api.types.effector_type_label import EffectorTypeLabels, TypeLabels
from api.utils import (
    DEFAULT_TTL,
    generate_cache_key,
    get_site_from_request,
    get_ttl,
    resolve_ttl,
    set_timestamp,
    strip_slash,
)
from directory.models.core import sync_clear_cache
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


async def _known_type(uid: str, request: Request, jwt: dict) -> None:
    await authorize_api("effector-types", request, jwt)
    if not await effector_type_exists(uid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EffectorType not found")


@router.get("/effector-types/{uid}/labels")
async def get_labels(uid: str, request: Request, jwt: Annotated[dict, Depends(JWT)]) -> TypeLabels:
    """One type's labels in every language, for the web UI to edit."""
    await _known_type(uid, request, jwt)
    return await get_type_labels(uid)


@router.put("/effector-types/{uid}/labels")
async def put_labels(
    uid: str, labels: TypeLabels, request: Request, jwt: Annotated[dict, Depends(JWT)]
) -> TypeLabels:
    """Replace one type's labels. Labels are shared by every site, so every
    site's cache of them is cleared, the v1 one included."""
    await _known_type(uid, request, jwt)
    await set_type_labels(uid, labels)
    for endpoint in ("v1:effector_type_labels", "v2:effector-type-labels"):
        await sync_to_async(sync_clear_cache)(endpoint)
    return await get_type_labels(uid)
