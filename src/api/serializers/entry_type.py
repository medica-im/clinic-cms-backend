"""Changing an entry's effector type.

An entry is (person, occupation, place): its HAS_EFFECTOR_TYPE edge is single
valued and nothing in the database enforces it, so the change replaces the
edge inside one transaction that checks the entry's shape before and after
(directory.entry_shape) and rolls back rather than leave it malformed.

Around the edge, what the occupation touches:
* the slug, which names the occupation, is regenerated; the old one is kept
  in directory.EntrySlug so its links redirect;
* tags whose category is not linked to the new occupation are removed (the
  page lists them first, from preview_removed_tags);
* the person is labelled HealthWorker when the new occupation is one.

Who may, and until when, is directory.entry_type_edit; the role comes from
this site's graph, like admin_entries and email_access. To which types is
directory.offered_types: the site's directory may limit them, superusers
excepted, the same set entry creation is held to.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from asgiref.sync import sync_to_async
from neomodel import adb

from api.neo4j_auth import get_neo4j_role, get_neo4j_user
from api.utils import get_site_from_request
from directory.entry_shape import entry_shape_problems
from directory.entry_type_edit import TypeEditPermission, type_edit_permission
from directory.models import EntrySlug
from directory.models.agraph import Entry as AgraphEntry
from directory.models.agraph import EffectorType as AgraphEffectorType
from directory.offered_types import TypeNotOffered, check_type_offered, site_directory_name
from directory.slug import generate_entry_slugs
from facility.models import Organization

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_DAYS = 30
DEFAULT_CONNECTED_DAYS = 7


class EntryTypeRefused(Exception):
    """code: same_type | duplicate (slug) | malformed (problems) | unknown_type
    | type_not_offered"""

    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class TypeEditContext:
    uid: str
    slug: str | None
    type_uid: str | None
    effector_uid: str | None
    facility_uid: str | None
    created_at_ms: int | None
    caller_uid: str | None
    permission: TypeEditPermission
    role: str | None = None
    # The site's directory, whose offered types hold; None: no limit known.
    directory: str | None = None


async def _one_uid(relationship) -> str | None:
    nodes = await relationship.all()
    return nodes[0].uid if len(nodes) == 1 else None


async def type_edit_context(uid: str, request, jwt: dict) -> TypeEditContext | None:
    """The entry and what the caller may do with its type; None when no entry
    has this uid."""
    entry = await AgraphEntry.nodes.get_or_none(uid=uid)
    if entry is None:
        return None
    site = await get_site_from_request(request)
    role = await get_neo4j_role(jwt, site) if jwt else None
    user = await get_neo4j_user(jwt) if jwt else None
    connected_uids = {u.uid for u in await entry.creator.all()} | {u.uid for u in await entry.owner.all()}
    organization = await Organization.objects.filter(site=site).afirst()
    permission = type_edit_permission(
        role=role,
        connected=bool(user and user.uid in connected_uids),
        created_at_ms=entry.createdAt,
        now=datetime.now(timezone.utc),
        admin_days=organization.entry_type_edit_days_administrator if organization else DEFAULT_ADMIN_DAYS,
        connected_days=organization.entry_type_edit_days_connected if organization else DEFAULT_CONNECTED_DAYS,
    )
    return TypeEditContext(
        uid=entry.uid,
        slug=entry.slug,
        type_uid=await _one_uid(entry.effector_type),
        effector_uid=await _one_uid(entry.effector),
        facility_uid=await _one_uid(entry.facility),
        created_at_ms=entry.createdAt,
        caller_uid=user.uid if user else None,
        permission=permission,
        role=role,
        directory=await site_directory_name(site),
    )


# A tag stays when it has no category (nothing ties it to an occupation), or
# when its category is linked to the new occupation.
UNFIT_TAGS = (
    "MATCH (tag:Tag)-[r:TAGS]->(e:Entry {uid: $entry}) "
    "WHERE (tag)-[:IS_A]->(:TagCategory) "
    "AND NOT (tag)-[:IS_A]->(:TagCategory)<-[:HAS_TAG_CATEGORY]-(:EffectorType {uid: $type}) "
)


async def preview_removed_tags(entry_uid: str, type_uid: str) -> list[dict]:
    rows, _ = await adb.cypher_query(
        UNFIT_TAGS + "RETURN tag.uid, coalesce(tag.label, tag.name) ORDER BY 2",
        {"entry": entry_uid, "type": type_uid},
    )
    return [{"uid": uid, "label": label} for uid, label in rows]


async def _duplicate_slug(context: TypeEditContext, type_uid: str) -> str | None:
    """Another entry -- active or not -- for this person, place and type."""
    rows, _ = await adb.cypher_query(
        "MATCH (other:Entry)-[:HAS_EFFECTOR]->(:Effector {uid: $effector}), "
        "(other)-[:HAS_FACILITY]->(:Facility {uid: $facility}), "
        "(other)-[:HAS_EFFECTOR_TYPE]->(:EffectorType {uid: $type}) "
        "WHERE other.uid <> $entry RETURN other.slug LIMIT 1",
        {"effector": context.effector_uid, "facility": context.facility_uid, "type": type_uid, "entry": context.uid},
    )
    return rows[0][0] if rows else None


async def change_entry_type(context: TypeEditContext, type_uid: str) -> dict:
    """Replace the entry's type; the caller has checked the permission.
    Returns {uid, slug, removed_tags}."""
    if type_uid == context.type_uid:
        raise EntryTypeRefused("same_type")
    new_type = await AgraphEffectorType.nodes.get_or_none(uid=type_uid)
    if new_type is None:
        raise EntryTypeRefused("unknown_type")
    if context.directory:
        try:
            await check_type_offered(context.directory, type_uid, context.role)
        except TypeNotOffered:
            raise EntryTypeRefused("type_not_offered")
    duplicate = await _duplicate_slug(context, type_uid)
    if duplicate is not None:
        raise EntryTypeRefused("duplicate", slug=duplicate)

    entry = await AgraphEntry.nodes.get(uid=context.uid)
    effector = await entry.effector.single()
    facility = await entry.facility.single()

    async with adb.transaction:
        problems = await entry_shape_problems(context.uid)
        if problems:
            raise EntryTypeRefused("malformed", problems=problems)
        await adb.cypher_query(
            "MATCH (e:Entry {uid: $entry})-[r:HAS_EFFECTOR_TYPE]->() DELETE r", {"entry": context.uid}
        )
        await adb.cypher_query(
            "MATCH (e:Entry {uid: $entry}), (t:EffectorType {uid: $type}) CREATE (e)-[:HAS_EFFECTOR_TYPE]->(t)",
            {"entry": context.uid, "type": type_uid},
        )
        rows, _ = await adb.cypher_query(
            UNFIT_TAGS + "DELETE r RETURN tag.uid, coalesce(tag.label, tag.name)",
            {"entry": context.uid, "type": type_uid},
        )
        removed_tags = [{"uid": uid, "label": label} for uid, label in rows]
        slugs = await generate_entry_slugs(effector, facility, new_type, count=1)
        new_slug = slugs[0] if slugs else context.slug
        await adb.cypher_query(
            "MATCH (e:Entry {uid: $entry}) SET e.slug = $slug, e.updatedAt = $now",
            {"entry": context.uid, "slug": new_slug, "now": time.time_ns() // 1_000_000},
        )
        problems = await entry_shape_problems(context.uid)
        if problems:
            # Raised inside the transaction, so nothing above is committed.
            logger.error(f"Entry {context.uid} malformed after its type change: {problems}")
            raise EntryTypeRefused("malformed", problems=problems)

    if context.slug and new_slug != context.slug:
        await sync_to_async(EntrySlug.objects.update_or_create)(
            slug=context.slug,
            defaults={"entry_uid": context.uid, "replaced_by": context.caller_uid or ""},
        )
    from api.serializers.entries import ensure_health_worker_label

    await ensure_health_worker_label(effector.uid, new_type)
    logger.info(
        f"Entry {context.uid} type {context.type_uid} -> {type_uid} by {context.caller_uid}; "
        f"slug {context.slug} -> {new_slug}; removed tags {[t['uid'] for t in removed_tags]}"
    )
    return {"uid": context.uid, "slug": new_slug, "removed_tags": removed_tags}
