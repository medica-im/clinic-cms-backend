import logging
from django.contrib.sites.models import Site
from fastapi import Request
from directory.models import Directory

logger = logging.getLogger(__name__)

async def get_site_from_request(request: Request) -> Site:
    try:
        return await Site.objects.aget(domain=request.url.hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {request.url.hostname} does not exist.'
        )
        raise e

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
