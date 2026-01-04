import logging
from fastapi import Request
from django.core.cache import cache
from api.utils import (
    generate_cache_key,
    get_directory,
    get_ttl,
    sync_get_site_from_request,
)
from directory.utils import (
    get_entries,
)
from directory.models.core import sync_set_timestamp
from directory.tasty.entries import createEntryResources

API_VERSION="v2"

logger=logging.getLogger(__name__)

TTL: int = 60

def get_object_list(request):
        directory=get_directory(request)
        logger.debug(f"{directory=}")
        nodes = get_entries(directory)
        logger.debug(f"{nodes[:1] if nodes else []}")
        contacts = createEntryResources(nodes, request)
        return contacts


async def get_all_entries(request: Request, jwt, role: str):
    cache_key = await generate_cache_key(
        API_VERSION,
        request
    )
    cached = cache.get(cache_key)
    if cached:
        logger.warning(f"*** Using cache with key {cache_key} ***")
        return cached
    else:
        logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
        value = get_object_list(request)
        timeout = get_ttl(API_VERSION, request) or TTL
        logger.debug(f"{timeout=}")
        cache.set(
            cache_key,
            value,
            timeout=timeout
        )
        path = request.scope['root_path'] + request.scope['route'].path
        endpoint = "%s:%s" % (API_VERSION, path)
        site = sync_get_site_from_request(request)
        sync_set_timestamp(endpoint, site)
        return value