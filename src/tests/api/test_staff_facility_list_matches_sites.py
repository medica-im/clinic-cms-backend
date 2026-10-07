"""The facilities offered when creating an entry, per role.

The entry creation form offers a list of facilities to choose from. It used to
be the facilities attached to the organization by PART_OF — an edge written
when a facility is created through the API, and by a one-off backfill for the
older ones. That backfill reached the organization through the directory's
OWNED_BY edge, which unipa's directory never had: 10 of the 18 facilities its
/sites page shows were attached to nothing, and an administrator could not
pick them.

**Base list (staff):** the /sites rule — every facility where an active entry
of the site's directory is located — plus the facilities attached by PART_OF
and those the user created. A facility just created, and not yet used by any
entry (an interrupted creation), must still be there on the second attempt.

**Repair list (administrators, superusers):** the base list plus the
facilities of the directory's inactive entries and those created by anyone who
ever had an access to the organization — current, superseded or suspended.
Users leave half-finished attempts behind; the people who repair them need to
see those, while staff are not offered other people's leftovers.

**Never another site's facility,** whoever created it. People work on several
sites — 4 of the 7 with an access to unipa's organization also have one to
santelyon3's — so "created by this user" or "by anyone linked" reached every
facility they had created in Lyon, and an administrator on unipa.fr could
attach an entry to a Lyon practice (2026-10-08). A facility belongs elsewhere
when it is attached to another organization or used by an entry of another
directory; the creator rules only add the ones that belong nowhere else.
"""
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "test-dir"
OTHER_DIRECTORY = "test-other-dir"

FACILITIES = (
    "at_active_entry", "part_of_only", "both", "at_inactive_entry", "other_directory",
    "created_by_me", "created_by_someone_else", "created_by_linked_user", "everything",
    # Another site's, created by someone this site knows.
    "other_site_created_by_me", "other_site_created_by_linked_user",
    "other_org_created_by_linked_user",
)


@pytest.fixture
async def graph(neo4j_graph):
    """One facility per case, all in the same commune; returns their uids by name."""
    from neomodel import adb

    uids = {
        name: uuid.uuid4().hex
        for name in (*FACILITIES, "org", "other_org", "me", "someone_else", "linked_user")
    }
    await adb.cypher_query(
        """
        CREATE (d:Directory {name: $dir})
        CREATE (od:Directory {name: $other_dir})
        CREATE (org:Entry {uid: $org, active: true})
        CREATE (other_org:Entry {uid: $other_org, active: true})
        CREATE (:User {uid: $me})
        CREATE (:User {uid: $someone_else})
        // Had an access to the organization, since superseded: still linked.
        CREATE (:User {uid: $linked_user})-[:HAS_ACCESS]->(:Access {role: 'staff', active: false})
               -[:ACCESS_TO]->(org)
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {
            uid: $cuid, name_fr: 'Lyon', slug_fr: 'lyon'
        })
        CREATE (dpt:DepartmentOfFrance {uid: $duid, name: 'Rhône', code: '69', slug: 'rhone', wikidata: 'Q12724'})
        CREATE (c)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        WITH d, od, org, other_org, c
        UNWIND [
            {uid: $at_active_entry,         dir: 'd',  active: true,  part_of: false, creator: null},
            {uid: $part_of_only,            dir: null, active: null,  part_of: true,  creator: null},
            {uid: $both,                    dir: 'd',  active: true,  part_of: true,  creator: null},
            {uid: $at_inactive_entry,       dir: 'd',  active: false, part_of: false, creator: null},
            {uid: $other_directory,         dir: 'od', active: true,  part_of: false, creator: null},
            {uid: $created_by_me,           dir: null, active: null,  part_of: false, creator: $me},
            {uid: $created_by_someone_else, dir: null, active: null,  part_of: false, creator: $someone_else},
            {uid: $created_by_linked_user,  dir: null, active: null,  part_of: false, creator: $linked_user},
            {uid: $everything,              dir: 'd',  active: true,  part_of: true,  creator: $me},
            {uid: $other_site_created_by_me,          dir: 'od', active: true, part_of: false, creator: $me},
            {uid: $other_site_created_by_linked_user, dir: 'od', active: true, part_of: false, creator: $linked_user},
            {uid: $other_org_created_by_linked_user,  dir: null, active: null, part_of: false, creator: $linked_user,
             part_of_other: true}
        ] AS spec
        CREATE (f:Facility {uid: spec.uid, name: spec.uid, slug: spec.uid})
        CREATE (f)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        FOREACH (_ IN CASE WHEN spec.part_of THEN [1] ELSE [] END |
            CREATE (f)-[:PART_OF]->(org))
        FOREACH (_ IN CASE WHEN spec.part_of_other THEN [1] ELSE [] END |
            CREATE (f)-[:PART_OF]->(other_org))
        FOREACH (_ IN CASE WHEN spec.dir = 'd' THEN [1] ELSE [] END |
            CREATE (d)-[:HAS_ENTRY]->(:Entry {uid: spec.uid + '-e', active: spec.active})-[:HAS_FACILITY]->(f))
        FOREACH (_ IN CASE WHEN spec.dir = 'od' THEN [1] ELSE [] END |
            CREATE (od)-[:HAS_ENTRY]->(:Entry {uid: spec.uid + '-e', active: spec.active})-[:HAS_FACILITY]->(f))
        WITH f, spec
        OPTIONAL MATCH (u:User {uid: spec.creator})
        FOREACH (_ IN CASE WHEN u IS NULL THEN [] ELSE [1] END |
            CREATE (f)-[:CREATED_BY]->(u))
        WITH f, spec
        // A second active entry at the facility matching every rule: one more
        // path to the same facility, the usual source of duplicated rows.
        MATCH (d:Directory {name: $dir})
        FOREACH (_ IN CASE WHEN spec.uid = $everything THEN [1] ELSE [] END |
            CREATE (d)-[:HAS_ENTRY]->(:Entry {uid: spec.uid + '-e2', active: true})-[:HAS_FACILITY]->(f))
        """,
        {
            "dir": DIRECTORY, "other_dir": OTHER_DIRECTORY,
            "cuid": uuid.uuid4().hex, "duid": uuid.uuid4().hex,
            **uids,
        },
    )
    return uids


async def listed(uids, *, repair=False):
    from api.serializers.facility import async_get_organization_facilities

    facilities = await async_get_organization_facilities(
        directory=DIRECTORY, org_entry_uid=uids["org"], user_uid=uids["me"], repair=repair
    )
    return [f.uid for f in facilities]


# --- Base list: staff --------------------------------------------------------


async def test_a_facility_at_an_active_entry_is_listed(graph):
    """The /sites rule: what the site shows can be picked."""
    assert graph["at_active_entry"] in await listed(graph)


async def test_a_facility_attached_but_unused_is_listed(graph):
    """Just created through the form, no entry yet: it must not vanish."""
    assert graph["part_of_only"] in await listed(graph)


async def test_a_facility_the_user_created_is_listed(graph):
    """Created by this user, not yet used by any entry and attached to nothing."""
    assert graph["created_by_me"] in await listed(graph)


@pytest.mark.parametrize("name", [
    "at_inactive_entry", "created_by_linked_user", "created_by_someone_else", "other_directory",
    "other_site_created_by_me", "other_site_created_by_linked_user", "other_org_created_by_linked_user",
])
async def test_the_base_list_leaves_out(graph, name):
    """No leftovers of other people's attempts, and nothing of another site."""
    assert graph[name] not in await listed(graph)


# --- Repair list: administrators and superusers -------------------------------


async def test_the_repair_list_adds_facilities_of_inactive_entries(graph):
    assert graph["at_inactive_entry"] in await listed(graph, repair=True)


async def test_the_repair_list_adds_facilities_created_by_anyone_linked(graph):
    """A former member's interrupted attempt is exactly what needs repairing."""
    assert graph["created_by_linked_user"] in await listed(graph, repair=True)


@pytest.mark.parametrize("name", [
    "created_by_someone_else", "other_directory",
    "other_site_created_by_me", "other_site_created_by_linked_user", "other_org_created_by_linked_user",
])
async def test_the_repair_list_still_leaves_out(graph, name):
    """Never linked to the organization, or another site's: still not offered."""
    assert graph[name] not in await listed(graph, repair=True)


async def test_the_repair_list_contains_the_base_list(graph):
    assert set(await listed(graph)) <= set(await listed(graph, repair=True))


# --- Either list is a set -----------------------------------------------------


@pytest.mark.parametrize("repair", [False, True])
async def test_the_list_is_a_set(graph, repair):
    """A facility reached by every rule, through two entries, still appears once."""
    uids = await listed(graph, repair=repair)
    assert uids.count(graph["everything"]) == 1
    assert uids.count(graph["both"]) == 1
    assert len(uids) == len(set(uids))
