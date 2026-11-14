"""Changing an entry's slug, and the redirect each change leaves.

The owner of an entry, administrators and superusers may rename a slug that reads
badly. The old slug has been shared, so it is kept in directory.EntrySlug and
/e/<old> redirects to the entry, whatever the number of renames since: a redirect
names the entry, not a slug. A slug another entry holds or held is never given
away, so an old link never leads to the wrong entry; an entry may take back one of
its own former slugs, which removes its redirect.
"""
import re
import time
from dataclasses import dataclass

from asgiref.sync import sync_to_async

from api.graph import read, write

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 255
SUGGESTIONS = 6


class EntrySlugRefused(Exception):
    """`code` is invalid, taken or unknown_entry."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class SlugEditContext:
    allowed: bool
    caller_uid: str | None


def slug_problem(slug: str) -> str | None:
    """'invalid' unless the slug is lowercase words and digits joined by single hyphens."""
    return None if slug and len(slug) <= SLUG_MAX and SLUG_PATTERN.match(slug) else "invalid"


def slug_edit_allowed(role: str | None, is_owner: bool) -> bool:
    return role in ("administrator", "superuser") or is_owner


async def slug_edit_context(uid: str, request, jwt: dict) -> SlugEditContext | None:
    """Whether the caller may change this entry's slug; None when no entry has this uid."""
    from api.neo4j_auth import get_neo4j_role, get_neo4j_user
    from api.utils import get_site_from_request

    if not await read("MATCH (e:Entry {uid: $u}) RETURN e.uid AS uid", u=uid):
        return None
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    user = await get_neo4j_user(jwt) if jwt else None
    is_owner = bool(user) and bool(
        await read("MATCH (:Entry {uid: $e})-[:OWNED_BY]->(u:User {uid: $u}) RETURN u.uid AS uid", e=uid, u=user.uid)
    )
    return SlugEditContext(allowed=slug_edit_allowed(role, is_owner), caller_uid=user.uid if user else None)


def _former_owner(slug: str) -> str | None:
    from directory.models import EntrySlug

    row = EntrySlug.objects.filter(slug=slug).first()
    return row.entry_uid if row else None


async def _taken(entry_uid: str, slug: str) -> bool:
    if await read("MATCH (e:Entry {slug: $s}) WHERE e.uid <> $u RETURN e.uid AS uid", s=slug, u=entry_uid):
        return True
    owner = await sync_to_async(_former_owner)(slug)
    return owner is not None and owner != entry_uid


async def _suggestions(entry_uid: str) -> list[str]:
    from neomodel import adb

    from directory.models.agraph import Entry
    from directory.slug import generate_entry_slugs

    if adb.driver is None:
        await adb.cypher_query("RETURN 1")
    entry = await Entry.nodes.get_or_none(uid=entry_uid)
    if entry is None:
        return []
    effectors, facilities, types = await entry.effector.all(), await entry.facility.all(), await entry.effector_type.all()
    if not (effectors and facilities and types):
        return []
    return await generate_entry_slugs(effectors[0], facilities[0], types[0], count=SUGGESTIONS)


async def check_entry_slug(entry_uid: str, slug: str) -> dict:
    """Whether `slug` may be this entry's, and the slugs it could have instead."""
    reason = slug_problem(slug) or ("taken" if await _taken(entry_uid, slug) else None)
    return {"slug": slug, "free": reason is None, "reason": reason, "suggestions": await _suggestions(entry_uid)}


def _record_former(slug: str, entry_uid: str, caller_uid: str | None) -> None:
    from directory.models import EntrySlug

    EntrySlug.objects.update_or_create(slug=slug, defaults={"entry_uid": entry_uid, "replaced_by": caller_uid or ""})


async def record_former_slug(slug: str | None, entry_uid: str, caller_uid: str | None) -> None:
    """Keep a slug the entry no longer carries, so /e/<slug> redirects to it."""
    if slug:
        await sync_to_async(_record_former)(slug, entry_uid, caller_uid)


def _forget_own_former(slug: str, entry_uid: str) -> None:
    from directory.models import EntrySlug

    EntrySlug.objects.filter(slug=slug, entry_uid=entry_uid).delete()


async def change_entry_slug(entry_uid: str, new_slug: str, caller_uid: str | None) -> str:
    """Give the entry `new_slug`, keeping its old slug as a redirect; the slug it now has."""
    rows = await read("MATCH (e:Entry {uid: $u}) RETURN e.slug AS slug", u=entry_uid)
    if not rows:
        raise EntrySlugRefused("unknown_entry")
    old = rows[0]["slug"]
    if new_slug == old:
        return old
    problem = slug_problem(new_slug) or ("taken" if await _taken(entry_uid, new_slug) else None)
    if problem:
        raise EntrySlugRefused(problem)
    await write(
        "MATCH (e:Entry {uid: $u}) SET e.slug = $s, e.updatedAt = $now",
        u=entry_uid, s=new_slug, now=time.time_ns() // 1_000_000,
    )
    await sync_to_async(_forget_own_former)(new_slug, entry_uid)
    await record_former_slug(old, entry_uid, caller_uid)
    return new_slug
