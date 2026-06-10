import logging
from common.utils import timestamp
from typing import Any
from neomodel import db, adb
from fastapi import HTTPException, Request
from django.db import IntegrityError
from addressbook.models import Contact
from directory.models import Directory
from directory.models.agraph import (
    Directory as AsyncDirectory,
    Entry as AsyncEntry,
    EffectorType as AsyncEffectorType,
    Effector as AsyncEffector,
    Facility as AsyncFacility,
    Organization as AsyncOrganization,
)
from api.serializers.fullentry import async_get_fullentry
from api.types.entry import Entry, EntryPost, EntryPatch
from api.types.effector import Effector
from api.types.fullentry import FullEntry, EffectorType
from api.types.facility import Facility
from api.utils import clear_cache, get_site_from_request
from access.asyncneomodels import User as AsyncUser
from api.neo4j_auth import get_neo4j_user, get_neo4j_role
from api.routers.utils import get_directory_from_hostname
from directory.slug import generate_entry_slugs
from access.models import Role

logger = logging.getLogger(__name__)

async def validate_access(access: str):
    if not await Role.objects.filter(name=access).aexists():
        raise HTTPException(
            status_code=422,
            detail=f"Invalid access role: '{access}'"
        )

def get_entries(
        effector_type: str|None = None,
        facility: str|None = None,
        effector: str|None = None,
        directory: Directory|None = None,
        uid: str|None = None,
        active: bool = True
    )->list[str]:
    if effector_type and facility and effector:
        query=(
            f"""MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector) WHERE effector.uid="{effector}" MATCH (entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid="{facility}" MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid="{effector_type}" RETURN DISTINCT entry.uid;"""
        )
    elif effector_type and facility:
        query=(
            f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid="{facility}" MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid="{effector_type}" RETURN DISTINCT entry.uid;""")
    q = db.cypher_query(query,resolve_objects = True)
    uids=[]
    if q:
        results = q[0]
        uids = [
            _uid
            for xs in results
            for _uid in xs
            
        ]
    return uids

async def entry_if_exists(effector: Effector, effector_type: EffectorType, facility: Facility):
    entry_uids: list[str] = get_entries(
        effector=effector.uid,
        effector_type=effector_type.uid,
        facility=facility.uid
    )
    if not entry_uids:
        logger.debug(f"No entry exists with:\n{effector=}\n{effector_type=}\n{facility=}")
        return
    active_entries: list[AsyncEntry] = []
    inactive_entries: list[AsyncEntry] = []
    for uid in entry_uids:
        entry: AsyncEntry = await AsyncEntry.nodes.get(uid=uid)
        if entry.active:
            active_entries.append(entry)
        else:
            inactive_entries.append(entry)
    if len(active_entries) > 1:
        detail=f"{len(active_entries)} active Entry objects with same effector, effector_type and facility already exist."
        logger.debug(detail)
        raise HTTPException(status_code=452, detail=detail)
    if len(active_entries) == 1:
        detail="One active Entry object with same effector, effector_type and facility already exists."
        logger.debug(detail)
        raise HTTPException(status_code=452, detail=detail)
    if len(inactive_entries) > 1:
        detail=f"{len(inactive_entries)} inactive Entry objects with same effector, effector_type and facility already exist."
        logger.debug(detail)
        raise HTTPException(status_code=452, detail=detail)
    if len(inactive_entries) == 1:
        entry = inactive_entries[0]
        entry.active = True  # type: ignore[reportAttributeAccessIssue]
        entry = await entry.save()
        logger.debug(f"Existing Entry found: {entry}")
        return entry

async def connect_member_of(new_entry, entry: EntryPost):
    if entry.memberships:
        for uid in entry.memberships:
            if not uid:
                continue
            try:
                org = await AsyncOrganization.nodes.get(uid=uid)
                await new_entry.organizations.connect(org)
            except Exception as e:
                logger.debug(e)
                try:
                    await adb.cypher_query(
                        'MATCH (a:Entry {uid: $a_uid}), (b:Entry {uid: $b_uid}) '
                        'MERGE (a)-[:MEMBER_OF]->(b)',
                        {'a_uid': new_entry.uid, 'b_uid': uid}
                    )
                except Exception as e:
                    logger.debug(e)
                    logger.error(f"No node (Organization or Entry) found for {uid=}")
                    raise Exception(e)

async def ensure_slug(entry_node, effector, facility, effector_type):
    """Assign a slug to an Entry node if it doesn't have one."""
    if entry_node.slug:
        return
    slugs = await generate_entry_slugs(effector, facility, effector_type, count=1)
    if slugs:
        entry_node.slug = slugs[0]  # type: ignore[reportAttributeAccessIssue]
        await entry_node.save()
    else:
        raise HTTPException(status_code=500, detail="Could not generate a unique slug for this entry.")


async def create_entry(entry: EntryPost, request: Request, jwt)-> FullEntry:
    await validate_access(entry.access)
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site)
    if entry.directory and role == "superuser":
        dir_name=entry.directory
    else:
        directory = await get_directory_from_hostname(request.url.hostname)
        dir_name=directory.name
    logger.debug(f"{dir_name}")  
    neo4j_directory = await AsyncDirectory.nodes.get(name=dir_name)
    effector: Effector = await AsyncEffector.nodes.get(uid=entry.effector)
    effector_type: AsyncEffectorType = await AsyncEffectorType.nodes.get(uid=entry.effector_type)
    facility: Facility = await AsyncFacility.nodes.get(uid=entry.facility)
    entry_uids: list[str] = get_entries(
        effector=effector.uid,
        effector_type=str(effector_type.uid),
        facility=facility.uid
    )
    logger.debug(f"{entry_uids=}")
    ms = timestamp()
    for uid in entry_uids:
        _entry: Entry = await AsyncEntry.nodes.get(uid=uid)
        createdAt = _entry.createdAt
        if createdAt:
            logger.debug(f"{ms=}")
            logger.debug(f"{createdAt=}")
            logger.debug(f'(ms - createdAt)<(1000*60*5): {(ms - createdAt)<(1000*60*5)}')
        if createdAt and ((ms - createdAt)<(1000*60*5)):
            await ensure_slug(_entry, effector, facility, effector_type)
            await clear_cache("v2:entries", request)
            return await async_get_fullentry(str(_entry.uid), request, jwt)
    new_entry = await entry_if_exists(effector, effector_type, facility)
    if not new_entry:
        new_entry = await AsyncEntry(access=entry.access).save()
        await new_entry.effector.connect(effector)
        await new_entry.effector_type.connect(effector_type)
        await new_entry.facility.connect(facility)
    neo4j_user = await get_neo4j_user(jwt)
    if neo4j_user:
        await new_entry.creator.connect(neo4j_user)  # type: ignore[reportAttributeAccessIssue]
        if entry.isOwner:
            await new_entry.owner.connect(neo4j_user)  # type: ignore[reportAttributeAccessIssue]
    if entry.redeemEmail:
        if role not in ("administrator", "superuser"):
            logger.error(f"Role {role} attempted to set redeemEmail")
            raise HTTPException(
                status_code=403,
                detail="Only administrators and superusers can set redeemEmail"
            )
        new_entry.redeemEmail = entry.redeemEmail
        await new_entry.save()
    if entry.memberships:
        await connect_member_of(new_entry, entry)
    await ensure_slug(new_entry, effector, facility, effector_type)
    await neo4j_directory.entries.connect(new_entry)
    try:
        await Contact.objects.acreate(neomodel_uid=new_entry.uid)
    except IntegrityError:
        pass
    if "HCW" in await effector_type.labels():
        query = f"""MATCH (e:Effector) WHERE e.uid="{effector.uid}" SET e:HealthWorker RETURN labels(e);"""
        result = db.cypher_query(query)
        #logger.debug(result[0][0][0])
        if "HealthWorker" not in result[0][0][0]:
            raise HTTPException(status_code=500, detail=f"Label 'HealthWorker' not applied to Effector {effector.uid} of type {effector_type.name_fr}")
    await clear_cache("v2:entries", request)
    return await async_get_fullentry(str(new_entry.uid), request, jwt)

async def get_entry(uid:str)->Entry:
    entry = await AsyncEntry.nodes.get(uid=uid)
    #logger.debug(entry.__properties__)
    return Entry.model_validate(entry.__properties__)

async def update_entry_memberships(entry, memberships: list[str]):
    if memberships is None:
        return False
    if not memberships:
        await entry.memberships.disconnect_all()
        return True
    connected_uids = [e.uid for e in await entry.memberships.all()]
    logger.debug(f"{connected_uids=}")
    if set(connected_uids) == set(memberships):
        return False
    for uid in memberships:
        if uid not in connected_uids:
            try:
                await adb.cypher_query(
                    'MATCH (a:Entry {uid: $a_uid}), (b:Entry {uid: $b_uid}) '
                    'MERGE (a)-[:MEMBER_OF]->(b)',
                    {'a_uid': entry.uid, 'b_uid': uid}
                )
            except Exception as e:
                logger.error(f"Failed to connect membership {uid}: {e}")
    for uid in connected_uids:
        if uid not in memberships:
            try:
                await adb.cypher_query(
                    'MATCH (a:Entry {uid: $a_uid})-[r:MEMBER_OF]->(b:Entry {uid: $b_uid}) '
                    'DELETE r',
                    {'a_uid': entry.uid, 'b_uid': uid}
                )
            except Exception as e:
                logger.error(f"Failed to disconnect membership {uid}: {e}")
    return True

async def update_entry_owners(entry, owners: list[str]):
    if owners is None:
        return False
    if not owners:
        await entry.owner.disconnect_all()
        return True
    connected_uids = [str(user.uid) for user in await entry.owner.all()]
    if set(connected_uids) == set(owners):
        return False
    for uid in owners:
        if uid not in connected_uids:
            try:
                user = await AsyncUser.nodes.get(uid=uid)
                await entry.owner.connect(user)
            except AsyncUser.DoesNotExist:
                logger.error(f"User with uid={uid} not found")
    for uid in connected_uids:
        if uid not in owners:
            try:
                user = await AsyncUser.nodes.get(uid=uid)
                await entry.owner.disconnect(user)
            except AsyncUser.DoesNotExist:
                logger.error(f"User with uid={uid} not found")
    return True


async def update_entry(uid:str, update_data: EntryPatch, request: Request, jwt: dict|None = None):
    entry = await AsyncEntry.nodes.get(uid=uid)
    keys = update_data.model_fields_set
    logger.debug(f"{keys=}")
    if 'carte_vitale' in keys:
        entry.carte_vitale = update_data.carte_vitale
    if 'payment' in keys:
        entry.payment = update_data.payment
    if 'third_party_payer' in keys:
        entry.third_party_payer = update_data.third_party_payer
    if 'convention' in keys:
        entry.convention = update_data.convention
    should_clear_cache = False
    if 'active' in keys:
        entry.active = update_data.active
        should_clear_cache = True
    if 'memberships' in keys and update_data.memberships is not None:
        if await update_entry_memberships(entry, update_data.memberships):
            should_clear_cache = True
    if 'owners' in keys and update_data.owners is not None:
        if await update_entry_owners(entry, update_data.owners):
            should_clear_cache = True
    if 'redeemEmail' in keys:
        site = await get_site_from_request(request)
        role = await get_neo4j_role(jwt, site) if jwt else None
        if role not in ("administrator", "superuser"):
            logger.error(f"Role {role} attempted to set redeemEmail")
            raise HTTPException(
                status_code=403,
                detail="Only administrators and superusers can set redeemEmail"
            )
        entry.redeemEmail = update_data.redeemEmail
    if 'access' in keys:
        await validate_access(update_data.access)
        entry.access = update_data.access
        should_clear_cache = True
    await entry.save()
    if should_clear_cache:
        await clear_cache("v2:entries", request)
    entry_data = entry.__properties__
    owner_nodes = await entry.owner.all()
    entry_data["owners"] = [str(user.uid) for user in owner_nodes]
    membership_nodes = await entry.memberships.all()
    entry_data["memberships"] = [str(m.uid) for m in membership_nodes]
    return Entry.model_validate(entry_data)