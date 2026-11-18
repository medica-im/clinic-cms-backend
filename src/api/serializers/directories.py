import logging
from neomodel import adb
from fastapi import Request
from directory.models import Directory
from api.types.directory import AvailableDirectory
from api.utils import get_site_from_request
from directory.utils import async_get_directory_for_site

logger = logging.getLogger(__name__)

async def get_available_directories(request: Request) -> list[AvailableDirectory]:
    site = await get_site_from_request(request)
    current_directory = await async_get_directory_for_site(site)
    results, _ = await adb.cypher_query(
        '''
        MATCH (start:Directory {name: $name})-[:OWNED_BY]->(e:Entry)
        MATCH (d:Directory)-[:OWNED_BY]->(e)
        RETURN DISTINCT d.name
        ''',
        {'name': current_directory.name}
    )
    if not results:
        logger.error(f"No Entry owner found for Neo4j Directory name={current_directory.name}")
        return []
    names = [row[0] for row in results]
    directories = [d async for d in Directory.objects.filter(name__in=names)]
    return [
        AvailableDirectory(name=d.name, display_name=d.display_name)
        for d in directories
    ]
