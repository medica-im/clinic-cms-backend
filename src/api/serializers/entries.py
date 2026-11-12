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
from directory.facility_slug import assign_facility_slug
from directory.offered_types import TypeNotOffered, check_type_offered
from api.identity_rights import check_identity_role
from directory.facets import ENTRY_FACETS, check_age_range
from directory.coverage import CoverageRefused, get_coverage, set_coverage, unknown_places
from directory.manages import ManagesRefused, get_manages, set_manages, unknown_slugs
from directory.run_by import RunByRefused, set_run_by
from directory.siret_rule import SiretMismatch, check_siren
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
            """MATCH (entry:Entry)-[:HAS_EFFECTOR]->(effector:Effector) WHERE effector.uid=$effector MATCH (entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid=$facility MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid=$effector_type RETURN DISTINCT entry.uid;"""
        )
    elif effector_type and facility:
        query=(
            """MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility) WHERE f.uid=$facility MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE et.uid=$effector_type RETURN DISTINCT entry.uid;""")
    params = {"effector": effector, "facility": facility, "effector_type": effector_type}
    q = db.cypher_query(query, params, resolve_objects = True)
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


async def ensure_health_worker_label(effector_uid: str, effector_type) -> None:
    """A person listed under a health-worker occupation (HCW) is labelled
    HealthWorker. Used when an entry is created and when its type changes."""
    if "HCW" not in await effector_type.labels():
        return
    rows, _ = await adb.cypher_query(
        "MATCH (e:Effector {uid: $uid}) SET e:HealthWorker RETURN labels(e)",
        {"uid": effector_uid},
    )
    if not rows or "HealthWorker" not in rows[0][0]:
        raise HTTPException(
            status_code=500,
            detail=f"Label 'HealthWorker' not applied to Effector {effector_uid} of type {effector_type.name_fr}",
        )


RUN_BY_REFUSALS = {"unknown_entry": 404, "unknown_porteur": 422, "cycle": 409, "siret_mismatch": 409}


def check_run_by_role(role: str | None, what: str = "run_by") -> None:
    check_identity_role(role, what)


async def check_siren_write(entry_uid: str, siren: str | None, role: str | None) -> None:
    """Refuse a SIREN the role may not set, or one that disagrees with a service's SIRET."""
    check_run_by_role(role, "siren")
    try:
        await check_siren(entry_uid, siren)
    except SiretMismatch:
        raise HTTPException(status_code=409, detail={"code": "siret_mismatch"})


async def apply_run_by(entry_uid: str, porteur_uid: str | None, role: str | None) -> None:
    """Set or detach an entry's porteur, for those who may."""
    check_run_by_role(role)
    try:
        await set_run_by(entry_uid, porteur_uid)
    except RunByRefused as refused:
        raise HTTPException(status_code=RUN_BY_REFUSALS[refused.code], detail={"code": refused.code})


async def apply_manages(entry_uid: str, slugs: list[str] | None) -> None:
    """Make `slugs` what the entry manages; None or empty clears it."""
    try:
        await set_manages(entry_uid, slugs or [])
    except ManagesRefused as refused:
        status = 404 if refused.code == "unknown_entry" else 422
        detail = {"code": refused.code}
        if refused.slugs:
            detail["slugs"] = refused.slugs
        raise HTTPException(status_code=status, detail=detail)


async def apply_coverage(entry_uid: str, uids: list[str] | None) -> None:
    """Make `uids` the places the entry answers for; None or empty clears them."""
    try:
        await set_coverage(entry_uid, uids or [])
    except CoverageRefused as refused:
        status = 404 if refused.code == "unknown_entry" else 422
        detail = {"code": refused.code}
        if refused.uids:
            detail["uids"] = refused.uids
        raise HTTPException(status_code=status, detail=detail)


async def covered_uids(entry_uid: str) -> list[str]:
    return [place["uid"] for place in await get_coverage(entry_uid)]


async def create_entry(entry: EntryPost, request: Request, jwt)-> FullEntry:
    await validate_access(entry.access)
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site)
    if entry.run_by is not None:
        check_run_by_role(role)
    if entry.siren is not None:
        check_run_by_role(role, "siren")
    if entry.manages:
        unknown = await unknown_slugs(entry.manages)
        if unknown:
            raise HTTPException(status_code=422, detail={"code": "unknown_target", "slugs": unknown})
    if entry.coverage:
        unknown = await unknown_places(entry.coverage)
        if unknown:
            raise HTTPException(status_code=422, detail={"code": "unknown_place", "uids": unknown})
    if entry.directory and role == "superuser":
        dir_name=entry.directory
    else:
        directory = await get_directory_from_hostname(request.url.hostname)
        dir_name=directory.name
    logger.debug(f"{dir_name}")
    # Before anything is written. Superusers may use any type; see
    # directory/offered_types.py.
    try:
        await check_type_offered(dir_name, entry.effector_type, role)
    except TypeNotOffered:
        raise HTTPException(status_code=409, detail={"code": "type_not_offered"})
    neo4j_directory = await AsyncDirectory.nodes.get(name=dir_name)
    effector: Effector = await AsyncEffector.nodes.get(uid=entry.effector)
    effector_type: AsyncEffectorType = await AsyncEffectorType.nodes.get(uid=entry.effector_type)
    facility: Facility = await AsyncFacility.nodes.get(uid=entry.facility)
    if await assign_facility_slug(str(facility.uid), entry.facility_slug):
        await clear_cache("v1:facilities", request)
        await clear_cache("v2:public/facilities", request)
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
    facets = {name: getattr(entry, name) for name in ENTRY_FACETS if getattr(entry, name) is not None}
    if entry.siren is not None or facets:
        if entry.siren is not None:
            new_entry.siren = entry.siren
        for name, value in facets.items():
            setattr(new_entry, name, value)
        await new_entry.save()
    if entry.run_by is not None:
        await apply_run_by(str(new_entry.uid), entry.run_by, role)
    if entry.manages:
        await apply_manages(str(new_entry.uid), entry.manages)
    if entry.coverage:
        await apply_coverage(str(new_entry.uid), entry.coverage)
    await ensure_slug(new_entry, effector, facility, effector_type)
    await neo4j_directory.entries.connect(new_entry)
    try:
        await Contact.objects.acreate(neomodel_uid=new_entry.uid)
    except IntegrityError:
        pass
    await ensure_health_worker_label(effector.uid, effector_type)
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


async def update_entry_directories(entry, directories: list[str]):
    if directories is None:
        return False
    connected_names_result, _ = await adb.cypher_query(
        'MATCH (d:Directory)-[:HAS_ENTRY]->(a:Entry {uid: $a_uid}) RETURN d.name',
        {'a_uid': entry.uid}
    )
    connected_names = [row[0] for row in connected_names_result]
    logger.debug(f"{connected_names=}")
    if set(connected_names) == set(directories):
        return False
    for name in directories:
        if name not in connected_names:
            try:
                await adb.cypher_query(
                    'MATCH (d:Directory {name: $d_name}), (a:Entry {uid: $a_uid}) '
                    'MERGE (d)-[:HAS_ENTRY]->(a)',
                    {'d_name': name, 'a_uid': entry.uid}
                )
            except Exception as e:
                logger.error(f"Failed to connect directory {name}: {e}")
    for name in connected_names:
        if name not in directories:
            try:
                await adb.cypher_query(
                    'MATCH (d:Directory {name: $d_name})-[r:HAS_ENTRY]->(a:Entry {uid: $a_uid}) '
                    'DELETE r',
                    {'d_name': name, 'a_uid': entry.uid}
                )
            except Exception as e:
                logger.error(f"Failed to disconnect directory {name}: {e}")
    return True


async def update_entry(uid:str, update_data: EntryPatch, request: Request, jwt: dict|None = None):
    entry = await AsyncEntry.nodes.get(uid=uid)
    keys = update_data.model_fields_set
    logger.debug(f"{keys=}")
    if {'age_min', 'age_max'} & keys:
        try:
            check_age_range(
                update_data.age_min if 'age_min' in keys else entry.age_min,
                update_data.age_max if 'age_max' in keys else entry.age_max,
            )
        except ValueError:
            raise HTTPException(status_code=422, detail={"code": "age_range"})
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
    if 'directories' in keys and update_data.directories is not None:
        site = await get_site_from_request(request)
        role = await get_neo4j_role(jwt, site) if jwt else None
        if role not in ("administrator", "superuser"):
            logger.error(f"Role {role} attempted to set directories")
            raise HTTPException(
                status_code=403,
                detail="Only administrators and superusers can set directories"
            )
        if await update_entry_directories(entry, update_data.directories):
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
    if 'run_by' in keys:
        site = await get_site_from_request(request)
        role = await get_neo4j_role(jwt, site) if jwt else None
        await apply_run_by(str(entry.uid), update_data.run_by, role)
        should_clear_cache = True
    if 'siren' in keys:
        site = await get_site_from_request(request)
        role = await get_neo4j_role(jwt, site) if jwt else None
        await check_siren_write(str(entry.uid), update_data.siren, role)
        entry.siren = update_data.siren
        should_clear_cache = True
    for facet in ENTRY_FACETS:
        if facet in keys:
            setattr(entry, facet, getattr(update_data, facet))
            should_clear_cache = True
    if 'manages' in keys:
        await apply_manages(str(entry.uid), update_data.manages)
        should_clear_cache = True
    if 'coverage' in keys:
        await apply_coverage(str(entry.uid), update_data.coverage)
        should_clear_cache = True
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
    directory_names_result, _ = await adb.cypher_query(
        'MATCH (d:Directory)-[:HAS_ENTRY]->(a:Entry {uid: $a_uid}) RETURN d.name',
        {'a_uid': entry.uid}
    )
    entry_data["directories"] = [row[0] for row in directory_names_result]
    porteur_result, _ = await adb.cypher_query(
        'MATCH (:Entry {uid: $uid})-[:RUN_BY]->(p:Entry) RETURN p.uid',
        {'uid': entry.uid}
    )
    entry_data["run_by"] = porteur_result[0][0] if porteur_result else None
    entry_data["manages"] = await get_manages(str(entry.uid))
    entry_data["coverage"] = await covered_uids(str(entry.uid))
    return Entry.model_validate(entry_data)