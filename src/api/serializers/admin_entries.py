import logging

from neomodel import adb

from api.types.admin_entry import (
    AdminEffectorType,
    AdminEntry,
    AdminFacility,
    AdminUser,
)

logger = logging.getLogger(__name__)

# Every entry in the directory, active and inactive alike, with the people and
# timestamps an administrator needs to audit it.
#
# Separate from directory.utils.get_entries_query rather than a flag on it: that
# query feeds the public addressbook and is tuned for it — it INNER-joins
# facility, commune, department and country, so an entry missing any of them
# vanishes. For a public card list that is right; for an audit table it is
# exactly backwards, since a half-configured entry is the one an administrator
# most needs to find. Everything here is OPTIONAL for that reason.
ADMIN_ENTRIES_QUERY = """
MATCH (d:Directory {name: $directory_name})-[:HAS_ENTRY]->(entry:Entry)
OPTIONAL MATCH (entry)-[:HAS_EFFECTOR]->(effector:Effector)
OPTIONAL MATCH (entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType)
OPTIONAL MATCH (entry)-[:HAS_FACILITY]->(f:Facility)
OPTIONAL MATCH (entry)-[:CREATED_BY]->(creator:User)
OPTIONAL MATCH (entry)-[:OWNED_BY]->(owner:User)
OPTIONAL MATCH (entry)<-[:HAS_ENTRY]-(dir:Directory)
RETURN
    entry,
    effector,
    et,
    f,
    COLLECT(DISTINCT {uid: creator.uid, name: creator.name}) AS creators,
    COLLECT(DISTINCT {uid: owner.uid, name: owner.name}) AS owners,
    COLLECT(DISTINCT dir.name) AS directories
ORDER BY entry.createdAt DESC
"""


# The related objects an owner or administrator can edit from /e/{slug}, as
# their accessor on Contact.
EDITABLE_RELATIONS = (
    "addresses",
    "phonenumbers",
    "emails",
    "websites",
    "socialnetworks",
    "appointments",
)


def last_modified_of(contact):
    """The most recent edit to anything hanging off this contact.

    Computed rather than stored. A denormalised column would have to be written
    by every path that touches any related object, and the one path that forgot
    would make the column lie without anything failing — which is precisely
    what happened to contactUpdatedAt, wired into all eight models' save() and
    still 0 on every entry in dev.

    Returns None when the contact has nothing attached: an entry with no
    contact data has never been modified, and the column shows a dash rather
    than a fabricated date.

    Deletion is the case this cannot see on its own — a deleted row takes its
    timestamp with it, so the max over the survivors can move backwards. The
    delete routes stamp the entry itself for that reason; see
    tests/test_entry_modification_timestamps.py::TestDeletionIsVisible.
    """
    if contact is None:
        return None
    # The contact's own stamp leads, because it is the one that survives a
    # related object being deleted — the receiver in addressbook.models moves
    # it on every post_delete.
    stamps = []
    # Read from the database rather than from the in-memory instance: the
    # post_delete receiver moves this column with a queryset update, which
    # cannot reach an object the caller is already holding.
    own = (
        type(contact)
        .objects.filter(pk=contact.pk)
        .values_list("updatedAt", flat=True)
        .first()
    )
    if own is not None:
        stamps.append(own)
    for relation in EDITABLE_RELATIONS:
        manager = getattr(contact, relation, None)
        if manager is None:
            continue
        for obj in manager.all():
            stamp = getattr(obj, "updatedAt", None)
            if stamp is not None:
                stamps.append(stamp)
    # Profile carries `updated` rather than `updatedAt` — it predates this and
    # keeps its own name; see TestProfileAlreadyHadThis.
    profile = getattr(contact, "profile", None)
    if profile is not None:
        stamp = getattr(profile, "updated", None)
        if stamp is not None:
            stamps.append(stamp)
    return max(stamps) if stamps else None


def _users(rows: list[dict]) -> list[AdminUser]:
    """Drop the empty maps an OPTIONAL MATCH leaves behind.

    COLLECT over a missing optional match yields [{uid: null, name: null}]
    rather than [], so an entry with no owner would otherwise arrive as one
    owner with no uid — and "has an owner" is precisely what an administrator
    reads this column to decide.
    """
    return [
        AdminUser(uid=row["uid"], name=row.get("name"))
        for row in rows
        if row and row.get("uid")
    ]


def _name_of(effector, entry) -> str | None:
    """The entry's display name.

    The Effector carries the person's name in the site's language; falling back
    to the entry slug keeps a half-configured entry identifiable in the table
    instead of showing a blank row.
    """
    if effector is not None:
        for attribute in ("name_fr", "name_en", "name"):
            value = getattr(effector, attribute, None)
            if value:
                return value
    return getattr(entry, "slug", None)


async def get_admin_entries(directory_name: str) -> list[AdminEntry]:
    """Every entry in one directory, with its administrative fields.

    Not cached, by design — see the router.
    """
    results, _ = await adb.cypher_query(
        ADMIN_ENTRIES_QUERY,
        {"directory_name": directory_name},
        resolve_objects=True,
    )

    entries: list[AdminEntry] = []
    for row in results:
        entry, effector, et, facility, creators, owners, directories = row
        # resolve_objects wraps collected rows in a single-element list.
        creators = creators[0] if creators else []
        owners = owners[0] if owners else []
        directories = directories[0] if directories else []

        entries.append(
            AdminEntry(
                uid=entry.uid,
                slug=getattr(entry, "slug", None),
                name=_name_of(effector, entry),
                active=bool(getattr(entry, "active", False)),
                createdAt=getattr(entry, "createdAt", None),
                updatedAt=getattr(entry, "updatedAt", None),
                deactivation_reason=getattr(entry, "deactivation_reason", None),
                deactivation_datetime=(
                    str(entry.deactivation_datetime)
                    if getattr(entry, "deactivation_datetime", None)
                    else None
                ),
                access=getattr(entry, "access", None) or "anonymous",
                effector_type=(
                    AdminEffectorType(
                        uid=et.uid,
                        name=getattr(et, "name_fr", None) or getattr(et, "name_en", None),
                        slug=getattr(et, "slug_fr", None) or getattr(et, "slug_en", None),
                    )
                    if et is not None
                    else None
                ),
                facility=(
                    AdminFacility(
                        uid=facility.uid,
                        name=getattr(facility, "label", None) or getattr(facility, "name", None),
                        slug=getattr(facility, "slug", None),
                    )
                    if facility is not None
                    else None
                ),
                directories=[d for d in directories if d],
                creators=_users(creators),
                owners=_users(owners),
            )
        )
    return entries
