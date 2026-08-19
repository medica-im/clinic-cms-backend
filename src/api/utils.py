import logging
import time
import copy
from typing import Any
from django.contrib.sites.models import Site
from access.models import Role
from fastapi import Request, HTTPException, status
from directory.models.api import Timestamp, Endpoint, TTL
from django.core.cache import cache
from django.db import DatabaseError
from directory.utils import async_get_directory_for_site
from directory.models.core import Directory
from facility.models import Organization
from directory.models.agraph import Entry

logger = logging.getLogger(__name__)

# How long a cached response lives when no TTL row says otherwise.
#
# One name, because this used to be three constants in three files answering
# the same question with different numbers: 60 in allentries, 60 in
# public_facilities, 3600 in situations. The 60s ones were the problem. A miss
# on v2:entries costs ~5s of regeneration on the largest site, and concurrent
# requests arriving during that gap do not share the work — each rebuilds the
# same dataset, so four at once took 12.5s apiece. Expiring every minute made
# that a routine event rather than a rare one.
#
# An hour is not a considered cache policy, it is a floor that keeps misses
# rare. Sites that want something else set a TTL row.
DEFAULT_TTL = 3600


def resolve_ttl(value: int | None, default: int = DEFAULT_TTL) -> int:
    """Pick between a configured TTL and the fallback.

    Exists because the call sites used ``await get_ttl(...) or DEFAULT``, and
    ``0`` is falsy in Python: a row saying "do not cache this at all" was
    silently turned into the default. Only ``None`` — no row — means "no
    answer", and only ``None`` should fall back.
    """
    return default if value is None else value


async def get_entry(entry_uid: str) -> Entry:
    try:
        return await Entry.nodes.get(uid=entry_uid)
    except Entry.DoesNotExist:
        raise HTTPException(status_code=404, detail="Entry not found")

async def get_entry_users(entry: Entry):
    return await entry.owner.all() or await entry.creator.all()

async def get_site_from_request(request: Request) -> Site:
    try:
        return await Site.objects.aget(domain=request.url.hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {request.url.hostname} does not exist.'
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN
        )

def sync_get_site_from_request(request: Request) -> Site:
    try:
        return Site.objects.get(domain=request.url.hostname)
    except Site.DoesNotExist as e:
        logger.error(
            f'Site with domain {request.url.hostname} does not exist.'
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN
        )


async def set_roles(object, roles):
    roles_qs=Role.objects.filter(name__in=roles)
    roles = []
    async for id in roles_qs.values_list('id', flat=True):
        roles.append(id)
    if roles:
        await object.roles.aset(roles)

async def set_timestamp(endpoint_name: str, site: Site):
    # timestamp unit: millisecond
    timestamp = int(time.time_ns()/1000000)
    try:
        endpoint = await Endpoint.objects.aget(name=endpoint_name)
    except Endpoint.DoesNotExist as e:
        logger.error(f"{endpoint_name=}\n{site=}\n{e}")
        return
    try:
        ts, _ = await Timestamp.objects.aget_or_create(endpoint=endpoint,site=site)
    except DatabaseError as e:
        logger.error(e)
        return
    ts.timestamp=timestamp
    await ts.asave()

async def clear_cache(endpoint: str, request: Request|None=None, site: Site|None=None):
    sites: list[Site] = []
    if site:
        sites.append(site)
    elif request:
        site = await get_site_from_request(request)
        sites.append(site)
    else:
        async for org in Organization.objects.select_related('site').filter(active=True).exclude(site__is_null=True).all():
            site = org.site
            if site:
                sites.append(site)
    for site in sites:
        cache_keys = []
        base_key = f"{endpoint}:{site.domain}"
        cache_keys.append(base_key)
        dir_names = [d.name async for d in Directory.objects.filter(site=site)]
        async for r in Role.objects.all():
            cache_keys.append(f"{base_key}:{r.name}")
            for dn in dir_names:
                cache_keys.append(f"{base_key}:{dn}:{r.name}")
        logger.debug(f"{cache_keys=}")
        for ck in cache_keys:
            deleted = cache.delete(ck)
            if deleted:
                logger.debug(f"cache {ck} {deleted=}")
        await set_timestamp(endpoint, site)

def strip_slash(path):
    if path[0] == '/':
        path = path[1:]
    if path[-1] == '/':
        path = path[:-1]
    return path

async def generate_cache_key(api_version: str, request: Request, role:str|None=None, directory_name:str|None=None):
        site = await get_site_from_request(request)
        domain = site.domain
        path = request.scope['route'].path
        path = strip_slash(path)
        cache_key = "%s:%s:%s" % (api_version, path, domain)
        if directory_name:
            cache_key = "%s:%s" % (cache_key, directory_name)
        if role:
            cache_key = "%s:%s" % (cache_key, role)
        return cache_key

async def get_directory(request):
    site = await get_site_from_request(request)
    return await async_get_directory_for_site(site)

async def get_ttl(api_version: str, request):
    path = request.scope['route'].path
    path = strip_slash(path)
    endpoint = "%s:%s" % (api_version, path)
    logger.debug(f"{endpoint=}")
    site = await get_site_from_request(request)
    # .afirst() returns None when nothing matches — it does not raise
    # DoesNotExist, so the except branch that used to be here could never run
    # and a site with no row of its own left no trace at all.
    # staging.santelyon3.fr ran on the fallback for months and nobody knew,
    # because the one line that would have said so was unreachable.
    ttl_obj = await TTL.objects.filter(endpoint__name=endpoint, site=site).afirst()
    if ttl_obj is None:
        logger.warning(
            "no TTL row for endpoint=%s site=%s; falling back to the default",
            endpoint, site,
        )
        return None
    return ttl_obj.ttl

ALLOWED_ACCESS = {
    "administrator": {"anonymous", "registered", "staff", "administrator"},
    "staff": {"anonymous", "registered", "staff"},
    "anonymous": {"anonymous"},
}

def scrub_avatar(entry: dict[str, Any], role: str):
    """Hide the avatar from viewers below its required access level.

    The avatar's "access" value is the minimum role needed to see the picture;
    viewers at that level or with higher privilege keep it, others get None so
    the frontend falls back to the placeholder.
    """
    avatar = entry.get("avatar")
    if not avatar:
        return
    required = avatar.get("access", "anonymous")
    allowed = ALLOWED_ACCESS.get(role)
    # Unknown roles (e.g. superuser) are not restricted.
    if allowed is not None and required not in allowed:
        entry["avatar"] = None

def process(entry: dict[str, Any], role: str, attributes: list[str]):
    #logger.debug(f'process {entry["name"]=}')
    if role not in ("administrator", "superuser"):
        entry.pop("redeemEmail", None)
    scrub_avatar(entry, role)
    for attribute in attributes:
        # Absent is normal, not an error: the attribute list is derived from
        # every role-bearing model, while each serializer emits its own subset
        # — allentries carries phones alone. Logging a miss per attribute per
        # entry buried the log in thousands of lines that meant nothing.
        if attribute not in entry:
            continue
        items: list[Any] = entry[attribute]
        if items:
            # Roles arrive as names ("staff"), not as objects — the serializers
            # emit a SlugRelatedField. Older payloads nested {"id", "name",
            # "description"} and this read role["name"]; both shapes are
            # accepted here because a cached response written before the change
            # outlives the deploy that made it.
            new_items = [
                item
                for item in items
                if role in [
                    r["name"] if isinstance(r, dict) else r
                    for r in item["roles"]
                ]
            ]
            new_count=len(new_items)
            count=len(items)
            if new_count != count:
                logger.debug(f"{count-new_count} item(s) removed!")
            entry[attribute] = new_items

def filter_by_access(entries: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    allowed = ALLOWED_ACCESS.get(role)
    if not allowed:
        return entries
    return [e for e in entries if e.get("access", "anonymous") in allowed]

def role_bearing_attributes() -> list[str]:
    """Payload keys holding a list of items that carry their own `roles`.

    Derived from the models rather than hand-listed. Seven addressbook models
    declare a `roles` M2M meaning "roles allowed so see the related object" —
    Address, PhoneNumber, Email, Website, SocialNetwork, Profile, Appointment —
    and every one of them was a field somebody had to remember to add to a
    literal list at each call site. Three were missed: websites, appointments
    and profile reached anonymous callers unfiltered because fullentry.py
    passed only ["phones", "emails", "socialnetworks"].

    Deriving it means the next role-bearing field is covered by existing to be
    serialised, not by being noticed.

    Two of the seven are deliberately excluded, and the exclusion is the reason
    this is a function rather than a comprehension over the app registry:
    `process` filters a *list* of items, and

      address  is serialised as a single dict  (types.fullentry.Address)
      profile  is serialised as a plain string (types.fullentry.profile: str)

    Neither can be filtered item-by-item, and feeding them here would raise or
    silently empty them. If either ever becomes a list of role-bearing rows,
    delete it from NOT_A_LIST_OF_ITEMS and it is covered automatically.
    """
    from django.apps import apps

    # Model class name -> the payload key, stated rather than guessed: the
    # obvious rule (lowercase and add an s) yields "addresss" and "profiles",
    # neither of which any serializer emits. A wrong key here is invisible —
    # `process` logs a KeyError and moves on — so the mapping is explicit and
    # the assertion below refuses to let one go stale.
    PAYLOAD_KEY = {
        "Address": None,        # a single dict, not a list of items
        "PhoneNumber": "phones",
        "Email": "emails",
        "Website": "websites",
        "SocialNetwork": "socialnetworks",
        "Profile": None,        # serialised as a plain string
        "Appointment": "appointments",
    }

    keys = []
    unmapped = []
    for model in apps.get_app_config("addressbook").get_models():
        if not any(f.name == "roles" for f in model._meta.get_fields()):
            continue
        if model.__name__ not in PAYLOAD_KEY:
            unmapped.append(model.__name__)
            continue
        key = PAYLOAD_KEY[model.__name__]
        if key is not None:
            keys.append(key)
    if unmapped:
        # A new role-bearing model reached the app without anyone deciding how
        # it is served. Loud, because the failure mode of staying quiet is
        # publishing restricted data.
        logger.error(
            "role-bearing model(s) %s have no payload key: their `roles` are "
            "NOT being enforced. Add them to PAYLOAD_KEY in "
            "api.utils.role_bearing_attributes.",
            ", ".join(sorted(unmapped)),
        )
    return sorted(keys)


def scrub(entries: list[dict[str, Any]], attributes: list[str]):
    logger.debug(f"scrub: {len(entries)} entries in, access values: {[e.get('access', 'anonymous') for e in entries[:5]]}")
    superuser = copy.deepcopy(entries)
    administrator = filter_by_access(copy.deepcopy(entries), "administrator")
    # Avatars restricted above the administrator level stay hidden for admins too.
    for entry in administrator:
        scrub_avatar(entry, "administrator")
    scrub_dct = {
        "superuser": superuser,
        "administrator": administrator,
    }
    for r in ["staff", "anonymous"]:
        #logger.debug(f"\n{'*'*(len(r)+4)}\n* {r} *\n{'*'*(len(r)+4)}")
        for entry in entries:
            process(entry, r, attributes)
        current_entries = filter_by_access(copy.deepcopy(entries), r)
        scrub_dct[r]=current_entries
    for r, e in scrub_dct.items():
        logger.debug(f"scrub: {r} -> {len(e)} entries")
    return scrub_dct