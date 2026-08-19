import logging

from neomodel import adb

from api.types.admin_entry import AdminEntry, AdminUser

logger = logging.getLogger(__name__)

# Only what /api/v2/entries does not already carry.
#
# The public feed serves an administrator every entry — access filtering does
# not apply above staff — with its name, slug, type, facility, commune,
# department, tags, directories, access and active state. The page has that
# payload in hand before this endpoint is called, because the root layout
# fetches it on every route. Repeating it here would mean a second walk over
# the same graph to produce data the browser already holds.
#
# So this query stays narrow: the entry uid to join on, the two timestamps the
# feed lacks, why it was deactivated, and the people involved with their names
# rather than bare uids.
ADMIN_ENTRIES_QUERY = """
MATCH (d:Directory {name: $directory_name})-[:HAS_ENTRY]->(entry:Entry)
OPTIONAL MATCH (entry)-[:CREATED_BY]->(creator:User)
OPTIONAL MATCH (entry)-[:OWNED_BY]->(owner:User)
RETURN
    entry.uid AS uid,
    entry.createdAt AS createdAt,
    entry.deactivation_reason AS deactivation_reason,
    toString(entry.deactivation_datetime) AS deactivation_datetime,
    COLLECT(DISTINCT {uid: creator.uid, name: creator.name}) AS creators,
    COLLECT(DISTINCT {uid: owner.uid, name: owner.name}) AS owners
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

    Deletion is the case a max() over the children cannot see on its own: a
    deleted row takes its timestamp with it, so the maximum can move backwards.
    The contact's own updatedAt is included first for that reason, moved by the
    post_delete receiver in addressbook.models, and it is read from the
    database rather than from the in-memory instance because that receiver
    writes with a queryset update.

    contact_timestamps() below is the bulk form used by the endpoint; this is
    the per-contact one, kept because it states the rule the bulk query
    depends on.
    """
    if contact is None:
        return None
    stamps = []
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
    # keeps its own name.
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


async def contact_timestamps(entry_uids: list[str]) -> dict[str, int]:
    """The last Postgres edit for each entry, in milliseconds.

    One query for the whole table rather than one per row. Contact carries the
    answer already: its own updatedAt is moved by every related object's save
    and by the post_delete receiver, so it covers phones, emails, websites,
    social networks, appointments and the avatar without visiting any of them.

    Keyed by the entry uid in hex, matching how neomodel stores node uids.
    """
    from addressbook.models import Contact

    stamps: dict[str, int] = {}
    uids = {u for u in entry_uids if u}
    if not uids:
        return stamps
    async for contact in Contact.objects.filter(neomodel_uid__in=uids).only(
        "neomodel_uid", "updatedAt"
    ):
        if contact.updatedAt is None:
            continue
        stamps[contact.neomodel_uid.hex] = int(contact.updatedAt.timestamp() * 1000)
    return stamps


async def get_admin_entries(directory_name: str) -> list[AdminEntry]:
    """The administrative fields for every entry in one directory.

    Not cached, by design — see the router.
    """
    results, _ = await adb.cypher_query(
        ADMIN_ENTRIES_QUERY, {"directory_name": directory_name}
    )

    stamps = await contact_timestamps([row[0] for row in results])

    return [
        AdminEntry(
            uid=uid,
            createdAt=createdAt,
            contactUpdatedAt=stamps.get(uid),
            deactivation_reason=deactivation_reason,
            deactivation_datetime=deactivation_datetime,
            creators=_users(creators),
            owners=_users(owners),
        )
        for (
            uid,
            createdAt,
            deactivation_reason,
            deactivation_datetime,
            creators,
            owners,
        ) in results
    ]
