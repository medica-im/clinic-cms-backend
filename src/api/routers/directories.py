import logging
from typing import Annotated
from fastapi import APIRouter, Request, Depends, HTTPException, status
from neomodel import adb
from api.types.directory import (
    AvailableDirectory,
    DirectoryOwner,
    DirectorySettings,
    DirectorySettingsUpdate,
    OfferedEffectorType,
    OfferedEffectorTypePost,
)
from api.serializers.directories import get_available_directories
from api.utils import clear_cache, get_site_from_request
from api.neo4j_auth import get_neo4j_role
from api.auth import JWT
from directory.offered_types import offer, withdraw, withdraw_all

logger = logging.getLogger(__name__)

router = APIRouter()

# Hard-coded rather than AccessControl rows, like the clone router: a row
# widening these is one careless edit away, a frozenset is not.
# Whether the organization's entry is listed: superusers only.
OWNER_SWITCH_ROLES = frozenset({"superuser"})
# The types a directory offers (directory/offered_types.py), and the page that
# shows both settings: administrators too.
OFFERED_TYPES_ROLES = frozenset({"superuser", "administrator"})

DIRECTORIES_QUERY = """
MATCH (d:Directory) WHERE d.name IN $names
OPTIONAL MATCH (d)-[:OWNED_BY]->(o:Entry)
OPTIONAL MATCH (o)-[:HAS_EFFECTOR]->(ef:Effector)
WITH d, head(collect({uid: o.uid, label: ef.name_fr})) AS owner
OPTIONAL MATCH (d)-[:OFFERS_EFFECTOR_TYPE]->(t:EffectorType)
WITH d, owner, t ORDER BY t.name_fr
WITH d, owner, [x IN collect({uid: t.uid, label: t.name_fr}) WHERE x.uid IS NOT NULL] AS types
RETURN d.uid, d.name, coalesce(d.list_owner_entry, true), owner, types
ORDER BY d.name
"""

SET_LIST_OWNER_ENTRY = """
MATCH (d:Directory {uid: $uid}) WHERE d.name IN $names
SET d.list_owner_entry = $value
RETURN d.name
"""

SITE_DIRECTORY = """
MATCH (d:Directory {uid: $uid}) WHERE d.name IN $names
RETURN d.name
"""


@router.get("/directories/available")
async def available_directories(request: Request, jwt: Annotated[dict, Depends(JWT)]) -> list[AvailableDirectory]:
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    if role not in ("administrator", "superuser"):
        raise HTTPException(status_code=403, detail="Only administrators and superusers can list directories")
    return await get_available_directories(request)


def _require(roles: frozenset[str]):
    async def dependency(request: Request, jwt: Annotated[dict, Depends(JWT)]):
        site = await get_site_from_request(request)
        role = await get_neo4j_role(jwt, site) if jwt else None
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return site
    return dependency


require_superuser = _require(OWNER_SWITCH_ROLES)
require_types_editor = _require(OFFERED_TYPES_ROLES)


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
            effector_types=[OfferedEffectorType(**t) for t in types],
        )
        for uid, name, listed, owner, types in rows
    ]


async def _one_of_this_site(uid: str, site) -> tuple[str, dict[str, str]]:
    """The directory's name, when it is one of this site's; 404 otherwise."""
    names = await _site_directories(site)
    rows, _ = await adb.cypher_query(SITE_DIRECTORY, {"uid": uid, "names": list(names)}, resolve_objects=False)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return rows[0][0], names


async def _settings_of(name: str, names: dict[str, str]) -> DirectorySettings:
    return (await _settings({name: names[name]}))[0]


@router.get("/directories")
async def directories(site: Annotated[object, Depends(require_types_editor)]) -> list[DirectorySettings]:
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
    return await _settings_of(name, names)


# One type at a time, never "replace with this set": two administrators
# editing at once would otherwise overwrite each other.

@router.post("/directories/{uid}/effector-types")
async def offer_effector_type(
    uid: str,
    body: OfferedEffectorTypePost,
    site: Annotated[object, Depends(require_types_editor)],
) -> DirectorySettings:
    name, names = await _one_of_this_site(uid, site)
    if not await offer(name, body.effector_type):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown effector type")
    return await _settings_of(name, names)


@router.delete("/directories/{uid}/effector-types/{type_uid}")
async def withdraw_effector_type(
    uid: str,
    type_uid: str,
    site: Annotated[object, Depends(require_types_editor)],
) -> DirectorySettings:
    name, names = await _one_of_this_site(uid, site)
    await withdraw(name, type_uid)
    return await _settings_of(name, names)


@router.delete("/directories/{uid}/effector-types")
async def withdraw_all_effector_types(
    uid: str,
    site: Annotated[object, Depends(require_types_editor)],
) -> DirectorySettings:
    """Back to the default: every type offered."""
    name, names = await _one_of_this_site(uid, site)
    await withdraw_all(name)
    return await _settings_of(name, names)
