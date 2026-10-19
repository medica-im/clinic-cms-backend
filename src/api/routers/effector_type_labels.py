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
from api.types.effector_type_label import EffectorTypeLabels, Language, TypeLabels
from api.utils import (
    DEFAULT_TTL,
    get_site_from_request,
    get_ttl,
    resolve_ttl,
    set_timestamp,
)
from directory.models.core import (
    effector_type_labels_cache_key,
    sync_clear_effector_type_labels_cache,
)
from facility.models import Organization

logger = logging.getLogger(__name__)

router = APIRouter()

API_VERSION = "v2"
TTL = DEFAULT_TTL


ENDPOINT = f"{API_VERSION}:effector-type-labels"


async def site_language(request: Request) -> str:
    try:
        organization = await Organization.objects.only("language").aget(
            site__domain=request.url.hostname
        )
    except Organization.DoesNotExist:
        logger.error(f"No organization for the site {request.url.hostname}.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return organization.language


@router.get("/effector-type-labels")
async def effector_type_labels(request: Request, language: Language | None = None) -> EffectorTypeLabels:
    """Effector-type labels in one language: the one asked for, else the
    requesting site's.

    The body is a bare uid -> labels object, with no envelope, as the v1
    endpoint it replaced served it.

    Labels belong to the whole backend, so the answer is cached once per
    language, whichever site asks; every write to labels clears every language
    (sync_clear_effector_type_labels_cache).
    """
    if language is None:
        language = await site_language(request)
    cache_key = effector_type_labels_cache_key(language)
    data = cache.get(cache_key)
    if data is not None:
        # Cached as a plain dict: the response model revalidates it on the way
        # out, so a stale entry whose shape no longer matches fails here rather
        # than reaching the frontend.
        return EffectorTypeLabels(data)

    labels = await get_effector_type_labels(language)
    timeout = resolve_ttl(await get_ttl(API_VERSION, request), TTL)
    # model_dump() rather than the model itself: the cache backend has to
    # serialise this, and a pydantic instance is not JSON.
    cache.set(cache_key, labels.model_dump(), timeout=timeout)
    await set_timestamp(ENDPOINT, await get_site_from_request(request))
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
    """Replace one type's labels, and clear every language's cached answer."""
    await _known_type(uid, request, jwt)
    await set_type_labels(uid, labels)
    await sync_to_async(sync_clear_effector_type_labels_cache)()
    return await get_type_labels(uid)
