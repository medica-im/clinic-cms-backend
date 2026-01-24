import logging
from fastapi import APIRouter, Request
from api.types.situation import Situation
from api.utils import get_directory
from pydantic import ValidationError
from directory.utils import async_entries_of_situation
from directory.models.agraph import  Situation as AsyncGraphSituation
from django.conf import settings
from api.utils import generate_cache_key, get_ttl, set_timestamp, get_site_from_request
from django.core.cache import cache

logger=logging.getLogger(__name__)

router = APIRouter()

API_VERSION="v2"
TTL=3600

@router.get("/situations")
async def situations(request: Request) -> list[Situation]:
    cache_key = await generate_cache_key(
        API_VERSION,
        request
    )
    data = cache.get(cache_key)
    if data:
        logger.warning(f"*** Using cache with key {cache_key} ***")
    else:
        logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
        directory = await get_directory(request)
        nodes = await AsyncGraphSituation.nodes.all()
        data = []
        for node in nodes:
            uid = node.uid
            name = getattr(
                node,
                f'name_{settings.LANGUAGE_CODE}',
                'name_en'
            )
            entries = await async_entries_of_situation(directory, node)
            situation = {
                "uid": uid,
                "name": name,
                "entries": entries
            }
            data.append(situation)
        timeout = await get_ttl(API_VERSION, request) or TTL
        cache.set(
                cache_key,
                data,
                timeout=timeout
            )
        path = request.scope['route'].path
        endpoint = "%s:%s" % (API_VERSION, path)
        site = await get_site_from_request(request)
        await set_timestamp(endpoint, site)
    return data



