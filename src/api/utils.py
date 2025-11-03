import logging
import time
from django.contrib.sites.models import Site
from access.models import Role
from fastapi import Request, HTTPException, status
from directory.models import Directory, Timestamp, Endpoint
from django.core.cache import cache
from facility.models import Organization
from django.contrib.sites.shortcuts import get_current_site

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

async def get_directory_from_hostname(hostname):
    try:
        site = await Site.objects.aget(domain=hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {hostname} does not exist.'
        )
        raise e
    try:
        return await Directory.objects.aget(site=site)
    except Directory.DoesNotExist as e:
        logger.error(
            f'Directory with site {site} does not exist.'
        )
        raise e

async def set_roles(object, roles):
    roles_qs=Role.objects.filter(name__in=roles)
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    if roles:
        await object.roles.aset(roles)

def sync_set_timestamp(endpoint_name: str, request):
    # timestamp unit: millisecond
    timestamp = int(time.time_ns()/1000000)
    site = get_current_site(request)
    try:
        endpoint=Endpoint.objects.get(name=endpoint_name)
    except Endpoint.DoesNotExist as e:
        logger.error(e)
        return
    ts, _ = Timestamp.objects.get_or_create(endpoint=endpoint,site=site)
    ts.timestamp=timestamp
    ts.save()

async def set_timestamp(endpoint_name: str, site: Site):
    # timestamp unit: millisecond
    timestamp = int(time.time_ns()/1000000)
    try:
        endpoint=Endpoint.objects.get(name=endpoint_name)
    except Endpoint.DoesNotExist as e:
        logger.error(e)
        return
    ts, _ = Timestamp.objects.get_or_create(endpoint=endpoint,site=site)
    ts.timestamp=timestamp
    ts.save()

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
        cache_key = f"{endpoint}:{site.domain}"
        deleted = cache.delete(cache_key)
        logger.debug(f"cache {cache_key} {deleted=}")
        await set_timestamp(endpoint, site)

def sync_clear_cache(endpoint: str, request: Request|None=None):
    sites: list[Site] = []
    if request:
        site = sync_get_site_from_request(request)
        sites.append(site)
    else:
        for org in Organization.objects.select_related('site').filter(active=True).exclude(site__is_null=True).all():
            site = org.site
            if site:
                sites.append(site)
    if not sites:
        return
    for site in sites:
        cache_key = f"{endpoint}:{site.domain}"
        deleted = cache.delete(cache_key)
        logger.debug(f"cache {cache_key} {deleted=}")
        sync_set_timestamp(endpoint, request)

