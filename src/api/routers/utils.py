from directory.models import Directory
from django.contrib.sites.models import Site
from directory.utils import async_get_directory_for_site
import logging

logger = logging.getLogger(__name__)

async def get_directory_from_hostname(hostname)->Directory:
    try:
        site = await Site.objects.aget(domain=hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {hostname} does not exist.'
        )
        raise e
    return await async_get_directory_for_site(site)
