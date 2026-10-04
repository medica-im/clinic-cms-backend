import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, HTTPException, status
from neomodel import adb
from api.types.directory import (
    AvailableDirectory,
    DirectoryOwner,
    DirectorySettings,
    DirectorySettingsUpdate,
)
from api.serializers.directories import get_available_directories
from api.utils import clear_cache, get_site_from_request
from api.neo4j_auth import get_neo4j_role
from api.auth import JWT

logger = logging.getLogger(__name__)

router = APIRouter()

# Hard-coded rather than an AccessControl row, like the clone router: a row
# widening this to administrators is one careless edit away, a frozenset is not.
SETTINGS_ROLES = frozenset({"superuser"})

DIRECTORIES_QUERY = """
MATCH (d:Directory) WHERE d.name IN $names
OPTIONAL MATCH (d)-[:OWNED_BY]->(o:Entry)
OPTIONAL MATCH (o)-[:HAS_EFFECTOR]->(ef:Effector)
WITH d, head(collect({uid: o.uid, label: ef.name_fr})) AS owner
RETURN d.uid, d.name, coalesce(d.list_owner_entry, true), owner
ORDER BY d.name
"""

SET_LIST_OWNER_ENTRY = """
MATCH (d:Directory {uid: $uid}) WHERE d.name IN $names
SET d.list_owner_entry = $value
RETURN d.name
"""


@router.get("/directories/available")
async def available_directories(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[AvailableDirectory]:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in ("administrator", "superuser"):
        raise HTTPException(status_code=403, detail="Only administrators and superusers can list directories")
    return await get_available_directories(request)


async def require_superuser(request: Request, jwt: Annotated[dict, Depends(JWT)]):
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in SETTINGS_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return site


async def _site_directories(site) -> dict[str, str]:
    """This site's directories, name -> display name (Django Directory.site)."""
    from directory.models import Directory
    return {d.name: d.display_name async for d in Directory.objects.filter(site=site)}


async def _settings(names: dict[str, str]) -> list[DirectorySettings]:
    rows, _ = await adb.cypher_query(DIRECTORIES_QUERY, {"names": list(names)}, resolve_objects=False)
    return [
        DirectorySettings(
            uid=uid,
            name=name,
            display_name=names.get(name),
            owner=DirectoryOwner(**owner) if owner and owner.get("uid") else None,
            list_owner_entry=listed,
        )
        for uid, name, listed, owner in rows
    ]


@router.get("/directories")
async def directories(site: Annotated[object, Depends(require_superuser)]) -> list[DirectorySettings]:
    return await _settings(await _site_directories(site))


@router.patch("/directories/{uid}")
async def update_directory(
    uid: str,
    body: DirectorySettingsUpdate,
    site: Annotated[object, Depends(require_superuser)],
) -> DirectorySettings:
    names = await _site_directories(site)
    rows, _ = await adb.cypher_query(
        SET_LIST_OWNER_ENTRY,
        {"uid": uid, "names": list(names), "value": body.list_owner_entry},
        resolve_objects=False,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Both lists filter on the switch; site= always, see clear_cache.
    await clear_cache("v2:entries", site=site)
    await clear_cache("v2:public/facilities", site=site)
    name = rows[0][0]
    return (await _settings({name: names[name]}))[0]
