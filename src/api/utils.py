import logging
from django.contrib.sites.models import Site
from access.models import Role
from fastapi import Request, HTTPException, status
from directory.models import Directory

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