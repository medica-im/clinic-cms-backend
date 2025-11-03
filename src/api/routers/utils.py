from directory.models import Directory
from django.contrib.sites.models import Site
import logging

logger = logging.getLogger(__name__)

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
