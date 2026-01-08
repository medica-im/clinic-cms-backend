import logging
import copy
from typing import Any
from pydantic import TypeAdapter
from fastapi import Request, HTTPException, status
from django.core.cache import cache
from django.conf import settings
from api.types.allentry import Entry
from api.utils import (
    generate_cache_key,
    get_directory,
    get_ttl,
    get_site_from_request,
    set_timestamp,
    scrub,
)
from directory.utils import (
    get_entries,
    async_get_phones_neomodel,
)
from adrf.serializers import Serializer
from rest_framework import serializers
from directory.models.core import Label
from directory.tasty.communes import createCommuneResources
from directory.tasty.types import (
    createEffectorTypeResources
)

API_VERSION="v2"

logger=logging.getLogger(__name__)

TTL: int = 60

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


class EntryObj(object):
    def __init__ (
            self,
            label,
            name,
            gender,
            slug,
            uid,
            effector_uid,
            effector_type,
            commune,
            department,
            address,
            phones,
            updatedAt,
            facility,
            avatar,
            memberships,
            employers,
            tags,
            active
        ):
        self.label = label
        self.name = name
        self.gender = gender
        self.slug = slug
        self.uid = uid
        self.effector_uid = effector_uid
        self.effector_type = effector_type
        self.commune = commune
        self.department = department
        self.address = address
        self.phones = phones
        self.updatedAt = updatedAt
        self.facility = facility
        self.avatar = avatar
        self.memberships = memberships
        self.employers = employers
        self.tags = tags
        self.active = active

async def createEntryResource(node):
    entry=node["entry"]
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
    updatedAt = max(
        [
            effector_node.updatedAt,
            node["facility"].contactUpdatedAt,
            entry.contactUpdatedAt,
        ]
    )
    facility = {
        "uid": node["facility"].uid,
        "name": node["facility"].name,
        "slug": node["facility"].slug,
        "label": node["facility"].label or node["facility"].name
    }
    avatar=node["avatar"]
    memberships=node["memberships"]
    employers=node["employers"]
    tags = None
    try:
        serializer = AsyncTagSerializer(node["tags"], many=True)
        tags = await serializer.adata
    except Exception as e:
        logger.error(e)
    active=entry.active

    entry = EntryObj(
        label,
        name,
        gender,
        slug,
        uid,
        effector_uid,
        effector_type,
        commune,
        department,
        address,
        phones,
        updatedAt,
        facility,
        avatar,
        memberships,
        employers,
        tags,
        active
    )
    return entry

async def createEntryResources(nodes: list, request):
    data= []
    # TODO manage Exception Value: 'NoneType' object is not iterable
    try:
        for node in nodes:
            data.append(await createEntryResource(node))
    except (TypeError, ValueError) as e:
        logger.error(e)
        pass
    return data

async def get_object_list(request):
        directory= await get_directory(request)
        logger.debug(f"{directory=}")
        nodes = await get_entries(directory)
        logger.debug(f"{nodes[:1] if nodes else []}")
        contacts = await createEntryResources(nodes, request)
        return contacts

def make_evil_twins(entries):
    uid_dct = {
        "administrator": "00000000-0000-4000-8000-000000000000",
        "staff": "00000000-0000-4000-8000-000000000001",
        "anonymous": "00000000-0000-4000-8000-000000000002"
    }
    twin_dct={}
    for r in ["administrator","staff", "anonymous"]:
        twin = copy.deepcopy(entries[0])
        twin.uuid=uid_dct[r]
        twin.label=r
        twin.name=r
        twin.slug=r
        twin_dct[r]=twin
    return twin_dct

def add_evil_twins(scrub_dct):
    if not settings.DEBUG:
        return
    twins: dict = make_evil_twins(scrub_dct["administrator"])
    for r in twins.keys():
        logger.debug(f"\ninserting {r} twin:\n{twins[r]}")
        entries = scrub_dct[r]
        logger.debug(f"scrub_dct[{r}] has {len(scrub_dct[r])} entries.")
        entries.insert(0, twins[r])
        logger.debug(f"scrub_dct[{r}] now has {len(scrub_dct[r])} entries.")

def normalize_role(role):
    if role == "registered":
        return "anonymous"
    elif role == "superuser":
        return "administrator"
    else:
        return role

async def get_all_entries(request: Request, jwt, role: str):
    role = normalize_role(role)
    logger.debug(f"normalized role: {role}")
    cache_key = await generate_cache_key(
        API_VERSION,
        request,
        role
    )
    cached = cache.get(cache_key)
    if cached:
        logger.warning(f"*** Using cache with key {cache_key} ***")
        return cached
    else:
        logger.warning(f"cache for key '{cache_key}' is *** EMPTY ***")
        raw = await get_object_list(request)
        timeout = await get_ttl(API_VERSION, request) or TTL
        logger.debug(f"{timeout=}")
        scrubbed_entries_dct = scrub(raw, ["phones"])
        add_evil_twins(scrubbed_entries_dct)
        for r in scrubbed_entries_dct.keys():
            cache_key = await generate_cache_key(
                API_VERSION,
                request,
                r
            )
            logger.debug(f"\nsetting cache\nrole: {r}\nkey: {cache_key}\n1st entry: {scrubbed_entries_dct[r][0].__dict__}\n{timeout=}")
            cache.set(
                cache_key,
                scrubbed_entries_dct[r],
                timeout=timeout
            )
        path = request.scope['route'].path
        endpoint = "%s:%s" % (API_VERSION, path)
        site = await get_site_from_request(request)
        await set_timestamp(endpoint, site)
        ta = TypeAdapter(list[Entry])
        return ta.validate_python(scrubbed_entries_dct[role])