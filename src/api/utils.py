import logging
import time
import copy
from typing import Any
from django.contrib.sites.models import Site
from access.models import Role
from fastapi import Request, HTTPException, status
from directory.models.api import Timestamp, Endpoint, TTL
from django.core.cache import cache
from django.db import DatabaseError
from directory.utils import async_get_directory_for_site
from directory.models.core import Directory
from facility.models import Organization
from directory.models.agraph import Entry

logger = logging.getLogger(__name__)

async def get_entry(entry_uid: str) -> Entry:
    try:
        return await Entry.nodes.get(uid=entry_uid)
    except Entry.DoesNotExist:
        raise HTTPException(status_code=404, detail="Entry not found")

async def get_entry_users(entry: Entry):
    return await entry.owner.all() or await entry.creator.all()

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
        logger.error(f"{endpoint_name=}\n{site=}\n{e}")
        return
    try:
        ts, _ = await Timestamp.objects.aget_or_create(endpoint=endpoint,site=site)
    except DatabaseError as e:
        logger.error(e)
        return
    ts.timestamp=timestamp
    await ts.asave()

async def clear_cache(endpoint: str, request: Request|None=None, site: Site|None=None):
    sites: list[Site] = []
    if site:
        sites.append(site)
    elif request:
        site = await get_site_from_request(request)
        sites.append(site)
    else:
        async for org in Organization.objects.select_related('site').filter(active=True).exclude(site__is_null=True).all():
            site = org.site
            if site:
                sites.append(site)
    for site in sites:
        cache_keys = []
        base_key = f"{endpoint}:{site.domain}"
        cache_keys.append(base_key)
        dir_names = [d.name async for d in Directory.objects.filter(site=site)]
        async for r in Role.objects.all():
            cache_keys.append(f"{base_key}:{r.name}")
            for dn in dir_names:
                cache_keys.append(f"{base_key}:{dn}:{r.name}")
        logger.debug(f"{cache_keys=}")
        for ck in cache_keys:
            deleted = cache.delete(ck)
            if deleted:
                logger.debug(f"cache {ck} {deleted=}")
        await set_timestamp(endpoint, site)

def strip_slash(path):
    if path[0] == '/':
        path = path[1:]
    if path[-1] == '/':
        path = path[:-1]
    return path

async def generate_cache_key(api_version: str, request: Request, role:str|None=None, directory_name:str|None=None):
        site = await get_site_from_request(request)
        domain = site.domain
        path = request.scope['route'].path
        path = strip_slash(path)
        cache_key = "%s:%s:%s" % (api_version, path, domain)
        if directory_name:
            cache_key = "%s:%s" % (cache_key, directory_name)
        if role:
            cache_key = "%s:%s" % (cache_key, role)
        return cache_key

async def get_directory(request):
    site = await get_site_from_request(request)
    return await async_get_directory_for_site(site)

async def get_ttl(api_version: str, request):
    path = request.scope['route'].path
    path = strip_slash(path)
    endpoint = "%s:%s" % (api_version, path)
    logger.debug(f"{endpoint=}")
    site = await get_site_from_request(request)
    try:
        ttl_obj = await TTL.objects.filter(endpoint__name=endpoint,site=site).afirst()
    except TTL.DoesNotExist as e:
        logger.error(f"TTL for {endpoint=} {site=} not found: {e}")
        return
    if ttl_obj:
        return ttl_obj.ttl

def process(entry: dict[str, Any], role: str, attributes: list[str]):
    #logger.debug(f'process {entry["name"]=}')
    if role not in ("administrator", "superuser"):
        entry.pop("redeemEmail", None)
    for attribute in attributes:
        try:
            items: list[Any] = entry[attribute]
        except KeyError as e:
            logger.error(e)
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
            entry[attribute] = new_items

ALLOWED_ACCESS = {
    "administrator": {"anonymous", "registered", "staff", "administrator"},
    "staff": {"anonymous", "registered", "staff"},
    "anonymous": {"anonymous"},
}

def filter_by_access(entries: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    allowed = ALLOWED_ACCESS.get(role)
    if not allowed:
        return entries
    return [e for e in entries if e.get("access", "anonymous") in allowed]

def scrub(entries: list[dict[str, Any]], attributes: list[str]):
    logger.debug(f"scrub: {len(entries)} entries in, access values: {[e.get('access', 'anonymous') for e in entries[:5]]}")
    superuser = copy.deepcopy(entries)
    administrator = filter_by_access(copy.deepcopy(entries), "administrator")
    scrub_dct = {
        "superuser": superuser,
        "administrator": administrator,
    }
    for r in ["staff", "anonymous"]:
        #logger.debug(f"\n{'*'*(len(r)+4)}\n* {r} *\n{'*'*(len(r)+4)}")
        for entry in entries:
            process(entry, r, attributes)
        current_entries = filter_by_access(copy.deepcopy(entries), r)
        scrub_dct[r]=current_entries
    for r, e in scrub_dct.items():
        logger.debug(f"scrub: {r} -> {len(e)} entries")
    return scrub_dct