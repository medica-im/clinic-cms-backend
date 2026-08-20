import logging
import copy
from typing import Any
from pydantic import TypeAdapter
from fastapi import Request, HTTPException, status
from django.core.cache import cache
from django.conf import settings
from api.types.allentry import Entry
from api.neo4j_auth import get_neo4j_role, normalize_neo4j_role
from api.utils import (
    role_bearing_attributes,
    DEFAULT_TTL,
    generate_cache_key,
    get_directory,
    get_ttl,
    get_site_from_request,
    resolve_ttl,
    set_timestamp,
    scrub,
    strip_slash
)
from directory.utils import (
    get_entries,
    async_get_phones_neomodel,
)
from adrf.serializers import Serializer
from rest_framework import serializers
from directory.models.core import Label
from api.transformers import createCommuneResources, createEffectorTypeResources

API_VERSION="v2"

logger=logging.getLogger(__name__)

# Re-exported so the name stays where callers expect it; the value lives in
# api.utils, which is the one place the fallback is decided.
TTL: int = DEFAULT_TTL

class AsyncTagSerializer(Serializer):
    uid = serializers.CharField()
    name = serializers.CharField()
    label = serializers.CharField()
    labelShort = serializers.CharField()
    category = serializers.DictField()
    effector_types = serializers.ListField()

    async def ato_representation(self, instance):
        effector_types=None
        category=None
        try:
            categories = await instance.tag_category.all()
            try:
                category = categories[0]
            except:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                    detail=f"Tag {instance} not linked to any category"
                )
            try:
                effector_types=[_type.uid for _type in await category.effector_type.all()]
            except Exception as e:
                    logger.error(e)
        except Exception as e:
            logger.error(e)
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "category": {
                "name": category.name,
                "label": category.label,
                "labelShort": category.labelShort,
            },
            "effector_types": effector_types
        }


async def flex_effector_type_label(
        effector,
        effector_type,
    ):
    try:
        effector_type_label= await Label.async_get_label(
            effector_type.uid,
            effector.gender,
            "S",
            settings.LANGUAGE_CODE
        )
    except Label.DoesNotExist as e:
        logger.error(e)
        effector_type_label=None
    try:
        name = effector_type.name
    except Exception as e:
        logger.error(e)
        name=None
    effector_type.label = effector_type_label or name
    return effector_type

def entry_updated_at(entry, effector, facility=None) -> int:
    """When this entry was last changed, across every node that carries it.

    The Entry's own `updatedAt` leads, because it is the thing being listed and
    because the APOC triggers maintain it on every property *and* relationship
    write — tags, memberships, access level, carte vitale all move it.

    It was absent from this max for a long time, which left the effector's
    stamp deciding. contactUpdatedAt is 0 on every node in the graph, so the
    answer was simply the effector's, and 21 of 22 entries on santelyon3
    reported a modification date earlier than their own creation date.

    The effector and facility stay in the max rather than being replaced: the
    effector carries the person's name and the facility their address, so an
    edit to either is an edit to the entry as a reader understands it.

    The facility contributes its `updatedAt`, not its `contactUpdatedAt`. That
    second field dates from when a facility's address was an addressbook row
    and `update_contact_timestamp` recorded changes to it; the address is now
    `street`/`zip`/`building`/`location` on the Facility node, so there is no
    Django contact data behind a facility for it to describe. Every write to
    the node stamps `updatedAt` through the APOC trigger instead — which is why
    `contactUpdatedAt` is not later than `updatedAt` on any of the 125 facility
    nodes that still carry one, and could never have won this max.

    `entry.contactUpdatedAt` stays: phones, emails and websites are still
    addressbook rows hanging off a Contact keyed to the entry.

    None is treated as 0 — a node predating one of these fields has no stamp,
    not a stamp of zero, and either way it must not win the max.
    """
    stamps = [
        getattr(entry, "updatedAt", 0) or 0,
        getattr(entry, "contactUpdatedAt", 0) or 0,
        getattr(effector, "updatedAt", 0) or 0,
    ]
    if facility is not None:
        stamps.append(getattr(facility, "updatedAt", 0) or 0)
    return max(stamps)


async def createEntryResource(node):
    entry = node["entry"]
    uid = entry.uid
    effector_node=node["effector"]
    address=node["address"]
    commune_node = node["commune"]
    commune_obj = createCommuneResources([commune_node])[0]
    commune = commune_obj.__dict__
    department = {
        "code": node["department"].code
    }
    label = getattr(
        effector_node,
        f'label_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'label_en',
            None
        )
    )
    name = getattr(
        effector_node,
        f'name_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'name_en',
            None
        )
    )
    gender = effector_node.gender
    slug = getattr(
        effector_node,
        f'slug_{settings.LANGUAGE_CODE}',
        getattr(
            effector_node,
            'slug_en',
            None
        )
    )
    effector_uid = effector_node.uid
    type_object = createEffectorTypeResources(node["effector_type"])
    type_object = await flex_effector_type_label(effector_node, type_object)
    effector_type = type_object.__dict__
    phones = await async_get_phones_neomodel(entry=entry)
    updatedAt = entry_updated_at(entry, effector_node, node["facility"])
    facility = {
        "uid": node["facility"].uid,
        "name": node["facility"].name,
        "slug": node["facility"].slug,
        "label": node["facility"].label or node["facility"].name
    }
    avatar=node["avatar"]
    memberships=node["memberships"]
    tags = None
    try:
        serializer = AsyncTagSerializer(node["tags"], many=True)
        tags = await serializer.adata
    except Exception as e:
        logger.error(e)
    active: bool = entry.active
    directories: list[str] = [d.name for d in node["directories"]]
    return {
        "label": label,
        "name": name,
        "gender": gender,
        "slug": slug,
        "entrySlug": entry.slug,
        "uid": uid,
        "effector_uid": effector_uid,
        "effector_type": effector_type,
        "commune": commune,
        "department": department,
        "address": address,
        "phones": phones,
        "updatedAt": updatedAt,
        "facility": facility,
        "avatar": avatar,
        "memberships": memberships,
        "tags": tags,
        "active": active,
        "directories": directories,
        "creator": node.get("creator_uids"),
        "owner": node.get("owner_uids"),
        "access": getattr(entry, 'access', 'anonymous'),
    }

async def createEntryResources(nodes: list, request):
    data: list[dict[str, Any]]= []
    # TODO manage Exception Value: 'NoneType' object is not iterable
    try:
        for node in nodes:
            data.append(await createEntryResource(node))
    except (TypeError, ValueError) as e:
        logger.error(e)
        pass
    return data

async def get_object_list(request, directory_name: str|None = None):
        if directory_name:
            from directory.models.core import Directory
            directory = await Directory.objects.select_related("site").aget(name=directory_name)
        else:
            directory = await get_directory(request)
        nodes = await get_entries(directory, active=None)
        #logger.debug(f"{nodes[:1] if nodes else []}")
        contacts = await createEntryResources(nodes, request)
        return contacts

def make_evil_twins(entries):
    uid_dct = {
        "administrator": "00000000000040008000000000000000",
        "staff": "00000000000040008000000000000001",
        "anonymous": "00000000000040008000000000000002"
    }
    twin_dct={}
    for r in ["administrator","staff", "anonymous"]:
        twin = copy.deepcopy(entries[0])
        twin["uid"]=uid_dct[r]
        twin["label"]=r
        twin["name"]=r
        twin["slug"]=r
        twin_dct[r]=twin
    return twin_dct

def add_evil_twins(scrub_dct):
    if not settings.DEBUG:
        return
    twins: dict = make_evil_twins(scrub_dct["administrator"])
    for r in twins.keys():
        entries = scrub_dct[r]
        entries.insert(0, twins[r])

async def get_all_entries(request: Request, jwt, directory_name: str|None = None)->list[Entry]:
    if directory_name:
        from directory.models.core import Directory
        directory = await Directory.objects.select_related("site").aget(name=directory_name)
    else:
        directory = await get_directory(request)
    dir_name = directory.name
    raw_role = await get_neo4j_role(jwt, directory.site) or "anonymous"
    role = normalize_neo4j_role(raw_role)
    logger.debug(f"normalized role: {role}")
    cache_key = await generate_cache_key(
        API_VERSION,
        request,
        role,
        directory_name=dir_name
    )
    entries = cache.get(cache_key)
    if entries:
        logger.warning(f"*** Using cache with key {cache_key} ***")
    else:
        logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
        raw = await get_object_list(request, directory_name=directory_name)
        # resolve_ttl, not `or`: a configured TTL of 0 means do not cache, and
        # `or` would read that as "no value" and substitute the default.
        timeout = resolve_ttl(await get_ttl(API_VERSION, request), TTL)
        logger.debug(f"{timeout=}")

        # Derived from the models that carry `roles`, so a field added to this
        # serializer later is filtered without anyone remembering to widen a
        # literal list here. Today only phones is emitted; the rest are no-ops
        # that log nothing and cost nothing.
        scrubbed_entries_dct = scrub(raw, role_bearing_attributes())
        #if settings.DEBUG:
        #    add_evil_twins(scrubbed_entries_dct)
        for r in scrubbed_entries_dct.keys():
            cache_key = await generate_cache_key(
                API_VERSION,
                request,
                r,
                directory_name=dir_name
            )
            #logger.debug(f"\nsetting cache\nrole: {r}\nkey: {cache_key}\n1st entry: {scrubbed_entries_dct[r][0]}\n2st entry: {scrubbed_entries_dct[r][1]}\n{timeout=}")
            cache.set(
                cache_key,
                scrubbed_entries_dct[r],
                timeout=timeout
            )
        path = request.scope['route'].path
        path = strip_slash(path)
        endpoint = "%s:%s" % (API_VERSION, path)
        site = await get_site_from_request(request)
        await set_timestamp(endpoint, site)
        entries = scrubbed_entries_dct[role]
    ta = TypeAdapter(list[Entry])
    return ta.validate_python(entries)