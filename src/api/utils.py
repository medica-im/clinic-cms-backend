import logging
import time
import copy
from typing import Any
from django.contrib.sites.models import Site
from access.models import Role
from fastapi import Request, HTTPException, status
from directory.models.api import Timestamp, Endpoint, TTL
from directory.models.core import Directory
from django.core.cache import cache
from facility.models import Organization
from django.db import DatabaseError

logger = logging.getLogger(__name__)

async def get_site_from_request(request: Request) -> Site:
    try:
        return await Site.objects.aget(domain=request.url.hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {request.url.hostname} does not exist.'
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN
        )

def sync_get_site_from_request(request: Request) -> Site:
    try:
        return Site.objects.get(domain=request.url.hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {request.url.hostname} does not exist.'
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN
        )


async def set_roles(object, roles):
    roles_qs=Role.objects.filter(name__in=roles)
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    if roles:
        await object.roles.aset(roles)

async def set_timestamp(endpoint_name: str, site: Site):
    # timestamp unit: millisecond
    timestamp = int(time.time_ns()/1000000)
    try:
        endpoint = await Endpoint.objects.aget(name=endpoint_name)
    except Endpoint.DoesNotExist as e:
        logger.error(e)
        return
    try:
        ts = await Timestamp.objects.aget(endpoint=endpoint,site=site)
    except Timestamp.DoesNotExist:
        try:
            ts = await Timestamp.objects.acreate(endpoint=endpoint,site=site)
        except DatabaseError as e:
            logger.error(e)
            return
    ts.timestamp=timestamp
    await ts.asave()

async def clear_cache(endpoint: str, request: Request|None=None):
    sites: list[Site] = []
    if request:
        site = await get_site_from_request(request)
        sites.append(site)
    else:
        async for org in Organization.objects.select_related('site').filter(active=True).exclude(site__is_null=True).all():
            site = org.site
            if site:
                sites.append(site)
    for site in sites:
        cache_keys = []
        cache_key = f"{endpoint}:{site.domain}"
        cache_keys.append(cache_key)
        async for r in Role.objects.all():
            cache_keys.append(f"{cache_key}:{r.name}")
        logger.debug(f"{cache_keys=}")
        for cache_key in cache_keys:
            deleted = cache.delete(cache_key)
            if deleted:
                logger.debug(f"cache {cache_key} {deleted=}")
        await set_timestamp(endpoint, site)

def strip_slash(path):
    if path[0] == '/':
        path = path[1:]
    if path[-1] == '/':
        path = path[:-1]
    return path

async def generate_cache_key(api_version: str, request: Request, role:str|None=None):
        site = await get_site_from_request(request)
        domain = site.domain
        path = request.scope['route'].path
        path = strip_slash(path)
        cache_key = "%s:%s:%s" % (api_version, path, domain)
        if role:
            cache_key = "%s:%s" % (cache_key, role)
        return cache_key

def sync_get_directory(request):
    site = sync_get_site_from_request(request)
    try:
        return Directory.objects.get(site=site)
    except Directory.DoesNotExist:
        raise Directory.DoesNotExist

async def get_directory(request):
    site = await get_site_from_request(request)
    try:
        return await Directory.objects.aget(site=site)
    except Directory.DoesNotExist:
        raise Directory.DoesNotExist

async def get_ttl(api_version: str, request):
    #path = request.scope['root_path'] + request.scope['route'].path
    path = request.scope['route'].path
    path = strip_slash(path)
    endpoint = "%s:%s" % (api_version, path)
    logger.debug(f"{endpoint=}")
    site = await get_site_from_request(request)
    try:
        ttl_obj = await TTL.objects.filter(endpoint__name=endpoint,site=site).afirst()
    except TTL.DoesNotExist:
        return
    if ttl_obj:
        return ttl_obj.ttl

def process(entry: object, role: str, attributes: list[str]):
    for attribute in attributes:
        try:
            items: list[Any] = getattr(entry, attribute)
        except:
            continue            
        if items:
            new_items = [
                item
                for item in items
                if (role in [role["name"] for role in item["roles"]])
            ] 
            new_count=len(new_items)
            count=len(items)
            if new_count != count:
                logger.debug(f"{count-new_count} item(s) removed!")
            setattr(entry, attribute, new_items)

def scrub(entries: list[object], attributes: list[str]):
    administrator = copy.deepcopy(entries)
    scrub_dct = {
        "administrator": administrator 
    }
    for r in ["staff", "anonymous"]:
        logger.debug(f"\n{'*'*(len(r)+4)}\n* {r} *\n{'*'*(len(r)+4)}")
        for entry in entries:
            process(entry, r,attributes)
        current_entries=copy.deepcopy(entries)
        scrub_dct[r]=current_entries
    return scrub_dct