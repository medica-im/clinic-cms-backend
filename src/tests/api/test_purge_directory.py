"""Removing a retired directory, and nothing that a live one still uses.

`manage.py purge_directory <name>` deletes what belonged to a retired project
(saint-esprit-sante.fr's `ses`, and the like) from both databases. What it
removes is decided by *exclusivity*, never by the directory alone:

* an Entry goes only if no other directory lists it; one that is shared just
  loses this directory;
* a person (Effector), a Facility, an Appointment goes only if every entry
  pointing at it goes — one person may hold entries in several directories
  (see test_entry_graph_model.py), and deleting them with the retired
  directory would delete a live job;
* the owner (an Organization or an Entry, via OWNED_BY) goes only if no other
  directory is owned by it and no surviving entry is a member of it;
* in Postgres: the Contact rows of the deleted entries and people, the
  Directory row, and — when the site has no other directory — the site with
  its Organization and that Organization's Facility rows.

`--dry-run` reports the counts and changes nothing. Postgres and Neo4j are
deleted inside one Django transaction, Neo4j last, so a failure in the graph
rolls Postgres back.
"""
import uuid

import pytest
from asgiref.sync import sync_to_async

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

RETIRED = "retired-dir"
LIVE = "live-dir"


@pytest.fixture
async def world(neo4j_graph, transactional_db):
    from neomodel import adb
    from django.contrib.sites.models import Site
    from addressbook.models import Contact
    from directory.models import Directory
    from facility.models import Facility, Organization

    u = {name: uuid.uuid4().hex for name in (
        "r_only", "r_shared_person", "in_both", "live",
        "person_only", "person_shared", "person_both",
        "fac_only", "fac_live", "org", "live_org",
    )}
    await adb.cypher_query(
        """
        CREATE (rd:Directory {uid: randomUUID(), name: $retired})
        CREATE (ld:Directory {uid: randomUUID(), name: $live_name})
        CREATE (org:Organization {uid: $org})
        CREATE (org)-[:OFFICIAL_WEBSITE]->(:Website {uid: randomUUID(), url: 'https://retired.example'})
        CREATE (rd)-[:OWNED_BY]->(org)
        CREATE (live_org:Entry {uid: $live_org, active: true})
        CREATE (ld)-[:OWNED_BY]->(live_org)
        CREATE (ld)-[:HAS_ENTRY]->(live_org)

        CREATE (fo:Facility {uid: $fac_only})
        CREATE (fl:Facility {uid: $fac_live})
        CREATE (fo)-[:PART_OF]->(org)

        // Only in the retired directory, its own person, place and appointment.
        CREATE (r1:Entry {uid: $r_only, active: true})
        CREATE (rd)-[:HAS_ENTRY]->(r1)
        CREATE (r1)-[:HAS_EFFECTOR]->(p1:Effector {uid: $person_only})
        CREATE (r1)-[:HAS_FACILITY]->(fo)
        CREATE (r1)-[:HAS_APPOINTMENT]->(:Appointment {uid: randomUUID()})
        CREATE (r1)-[:MEMBER_OF]->(org)
        CREATE (p1)-[:LOCATION]->(fo)

        // Only in the retired directory, but its person also works elsewhere.
        CREATE (r2:Entry {uid: $r_shared_person, active: true})
        CREATE (rd)-[:HAS_ENTRY]->(r2)
        CREATE (r2)-[:HAS_EFFECTOR]->(ps:Effector {uid: $person_shared})
        CREATE (r2)-[:HAS_FACILITY]->(fo)
        CREATE (r2)-[:MEMBER_OF]->(org)
        CREATE (ps)-[:MEMBER_OF]->(org)
        CREATE (ps)-[:LOCATION]->(fo)

        // Listed by both directories.
        CREATE (b:Entry {uid: $in_both, active: true})
        CREATE (rd)-[:HAS_ENTRY]->(b)
        CREATE (ld)-[:HAS_ENTRY]->(b)
        CREATE (b)-[:HAS_EFFECTOR]->(:Effector {uid: $person_both})
        CREATE (b)-[:HAS_FACILITY]->(fl)

        // Live only; shares the person of r2.
        CREATE (l:Entry {uid: $live, active: true})
        CREATE (ld)-[:HAS_ENTRY]->(l)
        CREATE (l)-[:HAS_EFFECTOR]->(ps)
        CREATE (l)-[:HAS_FACILITY]->(fl)
        CREATE (l)-[:MEMBER_OF]->(live_org)
        """,
        {**u, "retired": RETIRED, "live_name": LIVE},
    )

    @sync_to_async
    def seed_django():
        retired_site = Site.objects.create(domain="retired.example", name="Retired")
        live_site = Site.objects.create(domain="live.example", name="Live")
        Directory.objects.create(name=RETIRED, display_name="Retired", presentation="", site=retired_site)
        Directory.objects.create(name=LIVE, display_name="Live", presentation="", site=live_site)
        org = Organization.objects.create(name="retired-org", site=retired_site, neomodel_uid=uuid.UUID(u["org"]))
        Facility.objects.create(name="retired-facility", organization=org)
        for key in ("r_only", "r_shared_person", "in_both", "live", "person_only", "person_shared"):
            Contact.objects.create(neomodel_uid=uuid.UUID(u[key]))

    await seed_django()
    return u


async def purge(*args):
    from django.core.management import call_command
    await sync_to_async(call_command)("purge_directory", RETIRED, *args)


async def existing(uids):
    """The subset of these uids that still name a node."""
    from neomodel import adb
    rows, _ = await adb.cypher_query("MATCH (n) WHERE n.uid IN $uids RETURN n.uid", {"uids": list(uids)})
    return {row[0] for row in rows}


async def count(query, **params):
    from neomodel import adb
    rows, _ = await adb.cypher_query(query, params)
    return rows[0][0]


@sync_to_async
def contacts(uids):
    from addressbook.models import Contact
    return {c.neomodel_uid.hex for c in Contact.objects.filter(neomodel_uid__in=[uuid.UUID(x) for x in uids])}


class TestTheGraph:
    async def test_the_retired_directory_and_its_own_entries_go(self, world):
        await purge()
        assert await count("MATCH (d:Directory {name: $n}) RETURN count(d)", n=RETIRED) == 0
        assert await existing([world["r_only"], world["r_shared_person"]]) == set()

    async def test_an_entry_another_directory_lists_stays_there(self, world):
        await purge()
        assert await count(
            "MATCH (:Directory {name: $n})-[:HAS_ENTRY]->(e:Entry {uid: $uid}) RETURN count(e)",
            n=LIVE, uid=world["in_both"],
        ) == 1

    async def test_what_only_the_retired_entries_use_goes(self, world):
        await purge()
        assert await existing([world["person_only"], world["fac_only"]]) == set()
        assert await count("MATCH (a:Appointment) RETURN count(a)") == 0

    async def test_a_person_with_a_live_entry_stays(self, world):
        await purge()
        assert await existing([world["person_shared"], world["person_both"], world["fac_live"]]) == {
            world["person_shared"], world["person_both"], world["fac_live"],
        }
        assert await count(
            "MATCH (:Entry {uid: $uid})-[:HAS_EFFECTOR]->(p:Effector {uid: $p}) RETURN count(p)",
            uid=world["live"], p=world["person_shared"],
        ) == 1

    async def test_the_owner_organization_and_its_website_go(self, world):
        await purge()
        assert await existing([world["org"]]) == set()
        assert await count("MATCH (w:Website) RETURN count(w)") == 0

    async def test_the_live_directory_is_untouched(self, world):
        await purge()
        assert await existing([world["live"], world["live_org"]]) == {world["live"], world["live_org"]}
        assert await count("MATCH (:Directory {name: $n})-[:OWNED_BY]->(o) RETURN count(o)", n=LIVE) == 1


class TestPostgres:
    async def test_the_contacts_of_what_went_go(self, world):
        await purge()
        gone = [world["r_only"], world["r_shared_person"], world["person_only"]]
        kept = [world["in_both"], world["live"], world["person_shared"]]
        assert await contacts(gone) == set()
        assert await contacts(kept) == set(kept)

    async def test_the_site_with_no_other_directory_goes(self, world):
        from django.contrib.sites.models import Site
        from directory.models import Directory
        from facility.models import Facility, Organization

        await purge()

        @sync_to_async
        def remaining():
            return (
                set(Site.objects.filter(domain__in=["retired.example", "live.example"]).values_list("domain", flat=True)),
                set(Directory.objects.filter(name__in=[RETIRED, LIVE]).values_list("name", flat=True)),
                Organization.objects.filter(name="retired-org").exists(),
                Facility.objects.filter(name="retired-facility").exists(),
            )

        assert await remaining() == ({"live.example"}, {LIVE}, False, False)

    async def test_a_site_with_another_directory_stays(self, world):
        from django.contrib.sites.models import Site
        from directory.models import Directory
        from facility.models import Organization

        @sync_to_async
        def add_second_directory():
            Directory.objects.create(name="still-here", display_name="Still here", presentation="",
                                     site=Site.objects.get(domain="retired.example"))

        await add_second_directory()
        await purge()

        @sync_to_async
        def remaining():
            return (
                Site.objects.filter(domain="retired.example").exists(),
                Directory.objects.filter(name=RETIRED).exists(),
                Organization.objects.filter(name="retired-org").exists(),
            )

        assert await remaining() == (True, False, True)


class TestSafety:
    async def test_a_dry_run_changes_nothing(self, world):
        from django.contrib.sites.models import Site

        await purge("--dry-run")
        assert await existing(world.values()) == set(world.values())
        assert await count("MATCH (d:Directory {name: $n}) RETURN count(d)", n=RETIRED) == 1
        assert await sync_to_async(Site.objects.filter(domain="retired.example").exists)()

    async def test_an_unknown_directory_is_refused(self, world):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            await sync_to_async(call_command)("purge_directory", "no-such-directory")
