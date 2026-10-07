"""Whether a directory lists its owner — the organization's own entry.

A directory is owned by the organization's entry:

    (Directory)-[:OWNED_BY]->(Entry)

and that entry is also one of its members (HAS_ENTRY), so it shows in the
directory's address book and its facility on /sites. Some directories should
not list it. `Directory.list_owner_entry` decides, per directory:

* **On the Directory node, not the Entry.** Two directories may share an
  owner (santelyon3 and cpts-lyon-3-sante-mentale do); a property on the
  entry would hide it from both at once.
* **Absent means listed.** No migration: existing nodes keep today's
  behaviour, so the queries read `coalesce(d.list_owner_entry, true)`.
* **Filtered, never unlinked.** The HAS_ENTRY edge stays: redeem-email
  claiming (api/neo4j_auth.py) walks it from the organization's entry.
* **Lists only.** The entry's own page and the facility's own page stay
  reachable; only /entries and the /public/facilities list obey the switch.

Only superusers change it, through a role list hard-coded in the router rather
than an AccessControl row — see test_clone_authorization.py for why. Changing it
must drop both caches of the directory's site, or the switch seems not to work
until the TTL expires.
"""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "owner-test-dir"
SIBLING = "owner-test-sibling"
OTHER_SITE_DIRECTORY = "owner-test-elsewhere"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@pytest.fixture
async def graph(neo4j_graph):
    """Two directories sharing one owner; the owner and a member each at their own facility.

    Every entry carries what get_entries_query requires: effector, effector
    type, facility -> commune -> department -> country.
    """
    from neomodel import adb

    uids = {name: uuid.uuid4().hex for name in (
        "dir", "sibling", "elsewhere", "org", "member", "org_facility", "member_facility",
    )}
    await adb.cypher_query(
        """
        CREATE (country:Country {uid: randomUUID(), name: 'France'})
        CREATE (dpt:DepartmentOfFrance {uid: randomUUID(), name: 'Rhône', code: '69'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(country)
        CREATE (c:Commune:AdministrativeTerritorialEntityOfFrance {uid: randomUUID(), name_fr: 'Lyon', slug_fr: 'lyon'})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(dpt)
        CREATE (et:EffectorType {uid: randomUUID(), name_fr: 'Médecin', slug_fr: 'medecin'})
        CREATE (d:Directory {uid: $dir, name: $dir_name})
        CREATE (s:Directory {uid: $sibling, name: $sibling_name})
        CREATE (x:Directory {uid: $elsewhere, name: $elsewhere_name})
        WITH c, et, d, s, x
        UNWIND [
            {entry: $org,    facility: $org_facility},
            {entry: $member, facility: $member_facility}
        ] AS spec
        CREATE (f:Facility {uid: spec.facility, name: spec.facility, slug: spec.facility})
               -[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY]->(c)
        CREATE (e:Entry {uid: spec.entry, active: true})-[:HAS_FACILITY]->(f)
        CREATE (e)-[:HAS_EFFECTOR_TYPE]->(et)
        CREATE (e)-[:HAS_EFFECTOR]->(:Effector {uid: randomUUID(), name_fr: spec.entry})
        CREATE (d)-[:HAS_ENTRY]->(e)
        CREATE (s)-[:HAS_ENTRY]->(e)
        WITH d, s, x
        MATCH (org:Entry {uid: $org})
        CREATE (d)-[:OWNED_BY]->(org)
        CREATE (s)-[:OWNED_BY]->(org)
        CREATE (x)-[:OWNED_BY]->(org)
        """,
        {
            **uids,
            "dir_name": DIRECTORY, "sibling_name": SIBLING, "elsewhere_name": OTHER_SITE_DIRECTORY,
        },
    )
    return uids


async def set_flag(name, value):
    from neomodel import adb
    await adb.cypher_query(
        "MATCH (d:Directory {name: $name}) SET d.list_owner_entry = $value",
        {"name": name, "value": value},
    )


async def listed_entries(directory_name):
    from neomodel import adb
    from directory.utils import get_entries_query

    query = get_entries_query(SimpleNamespace(name=directory_name), active=None)
    rows, _ = await adb.cypher_query(query, resolve_objects=False)
    return [row[0] for row in rows]


async def listed_facilities(directory_name):
    from api.routers.public_facilities import _get_facility_nodes

    rows = await _get_facility_nodes(directory_name)
    return [facility.uid for facility, _commune, _country in rows]


class TestTheEntriesList:
    async def test_the_owner_is_listed_when_the_directory_says_nothing(self, graph):
        assert set(await listed_entries(DIRECTORY)) == {graph["org"], graph["member"]}

    async def test_the_owner_is_listed_when_asked(self, graph):
        await set_flag(DIRECTORY, True)
        assert set(await listed_entries(DIRECTORY)) == {graph["org"], graph["member"]}

    async def test_the_owner_is_left_out_when_the_directory_says_so(self, graph):
        await set_flag(DIRECTORY, False)
        assert await listed_entries(DIRECTORY) == [graph["member"]]

    async def test_the_switch_belongs_to_one_directory(self, graph):
        """Same owner, another directory: still listed there."""
        await set_flag(DIRECTORY, False)
        assert set(await listed_entries(SIBLING)) == {graph["org"], graph["member"]}

    async def test_the_owner_stays_a_member(self, graph):
        """Hidden, not unlinked: redeem-email claiming walks this edge."""
        from neomodel import adb

        await set_flag(DIRECTORY, False)
        rows, _ = await adb.cypher_query(
            "MATCH (:Directory {name: $name})-[r:HAS_ENTRY]->(:Entry {uid: $org}) RETURN count(r)",
            {"name": DIRECTORY, "org": graph["org"]},
        )
        assert rows[0][0] == 1


class TestThePublicFacilitiesList:
    async def test_the_owners_facility_is_listed_when_the_directory_says_nothing(self, graph):
        assert set(await listed_facilities(DIRECTORY)) == {graph["org_facility"], graph["member_facility"]}

    async def test_a_facility_only_the_owner_uses_is_left_out(self, graph):
        await set_flag(DIRECTORY, False)
        assert await listed_facilities(DIRECTORY) == [graph["member_facility"]]

    async def test_a_facility_a_member_also_uses_stays(self, graph):
        """The owner hidden does not hide a place where others practise."""
        from neomodel import adb

        await adb.cypher_query(
            """
            MATCH (m:Entry {uid: $member})-[r:HAS_FACILITY]->(), (f:Facility {uid: $org_facility})
            DELETE r CREATE (m)-[:HAS_FACILITY]->(f)
            """,
            {"member": graph["member"], "org_facility": graph["org_facility"]},
        )
        await set_flag(DIRECTORY, False)
        assert await listed_facilities(DIRECTORY) == [graph["org_facility"]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@contextmanager
def mock_role(role_name):
    """Patch the role lookup where the directories router imports it."""
    with patch("api.routers.directories.get_neo4j_role", new_callable=AsyncMock, return_value=role_name):
        yield


@pytest.fixture
async def django_directories(site, transactional_db, graph):
    """The two shared-owner directories belong to this site; the third to another."""
    from django.contrib.sites.models import Site
    from directory.models import Directory

    elsewhere, _ = await Site.objects.aget_or_create(domain="elsewhere.example", defaults={"name": "Elsewhere"})
    for name, owner_site in ((DIRECTORY, site), (SIBLING, site), (OTHER_SITE_DIRECTORY, elsewhere)):
        await Directory.objects.acreate(name=name, display_name=name, presentation="", site=owner_site)
    return graph


REFUSED = ["administrator", "staff", "registered"]
# Administrators read the list: the same page sets the types a directory
# offers (test_directory_offered_effector_types.py), which they may change.
# This switch they still may not.
LISTING_REFUSED = ["staff", "registered"]


class TestOnlySuperusersMayChangeIt:
    @pytest.mark.parametrize("role", LISTING_REFUSED)
    async def test_listing_is_refused(self, client, patch_jwt, jwt_superuser, django_directories, role):
        with patch_jwt(jwt_superuser), mock_role(role):
            r = await client.get("/directories")
        assert r.status_code == 403

    @pytest.mark.parametrize("role", REFUSED)
    async def test_changing_is_refused(self, client, patch_jwt, jwt_superuser, django_directories, role):
        with patch_jwt(jwt_superuser), mock_role(role):
            r = await client.patch(f"/directories/{django_directories['dir']}", json={"list_owner_entry": False})
        assert r.status_code == 403
        assert set(await listed_entries(DIRECTORY)) == {django_directories["org"], django_directories["member"]}

    async def test_anonymous_is_refused(self, client, django_directories):
        r = await client.patch(f"/directories/{django_directories['dir']}", json={"list_owner_entry": False})
        assert r.status_code == 401


class TestTheDirectoriesPage:
    async def test_lists_this_sites_directories_with_their_owner(self, client, patch_jwt, jwt_superuser, django_directories):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            r = await client.get("/directories")
        assert r.status_code == 200
        by_name = {d["name"]: d for d in r.json()}
        assert set(by_name) == {DIRECTORY, SIBLING}
        assert by_name[DIRECTORY]["uid"] == django_directories["dir"]
        assert by_name[DIRECTORY]["owner"]["uid"] == django_directories["org"]
        assert by_name[DIRECTORY]["list_owner_entry"] is True

    async def test_a_directory_without_owner_says_so(self, client, patch_jwt, jwt_superuser, django_directories):
        from neomodel import adb

        await adb.cypher_query("MATCH (:Directory {name: $name})-[r:OWNED_BY]->() DELETE r", {"name": SIBLING})
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            r = await client.get("/directories")
        assert {d["name"]: d["owner"] for d in r.json()}[SIBLING] is None

    async def test_turning_it_off_hides_the_owner(self, client, patch_jwt, jwt_superuser, django_directories):
        with patch_jwt(jwt_superuser), mock_role("superuser"), \
                patch("api.routers.directories.clear_cache", new_callable=AsyncMock):
            r = await client.patch(f"/directories/{django_directories['dir']}", json={"list_owner_entry": False})
        assert r.status_code == 200
        assert r.json()["list_owner_entry"] is False
        assert await listed_entries(DIRECTORY) == [django_directories["member"]]

    async def test_turning_it_off_clears_both_caches_of_the_site(self, client, patch_jwt, jwt_superuser, site,
                                                                 django_directories):
        with patch_jwt(jwt_superuser), mock_role("superuser"), \
                patch("api.routers.directories.clear_cache", new_callable=AsyncMock) as clear:
            await client.patch(f"/directories/{django_directories['dir']}", json={"list_owner_entry": False})
        cleared = {(call.args[0], call.kwargs.get("site")) for call in clear.await_args_list}
        assert cleared == {("v2:entries", site), ("v2:public/facilities", site)}

    async def test_an_unknown_directory_is_not_found(self, client, patch_jwt, jwt_superuser, django_directories):
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            r = await client.patch(f"/directories/{uuid.uuid4().hex}", json={"list_owner_entry": False})
        assert r.status_code == 404

    async def test_another_sites_directory_is_not_found(self, client, patch_jwt, jwt_superuser, django_directories):
        """A superuser here is not one of the other site's directories."""
        with patch_jwt(jwt_superuser), mock_role("superuser"):
            r = await client.patch(f"/directories/{django_directories['elsewhere']}", json={"list_owner_entry": False})
        assert r.status_code == 404
