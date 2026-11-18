"""A directory's owner follows its Organization.

Who owns a directory is said in Django — `Organization.directory` and
`Organization.neomodel_uid`, the uid of the organization's entry — and read in
Neo4j:

    (Directory)-[:OWNED_BY]->(Entry)

The directories settings page, the owner filter of the lists and the directory
picker all read the edge. It used to exist only once someone ran
`link_directory_owners` by hand, so a site set up without that step showed "no
organization" while its Organization said otherwise (unipa.fr, 2026-10).
Saving an Organization now writes the edge.

* **Only add, never remove.** Django cannot say everything Neo4j does: the
  OneToOne holds one directory per organization, while santelyon3 and
  cpts-lyon-3-sante-mentale share one owner, the second known to Neo4j alone.
  A sync that removed what Django does not mention would cut that edge. An
  organization moved to another directory leaves the old edge in place.
* **After the commit.** Neo4j does not roll back with Postgres; the edge is
  written once the row is committed.
* **Never in the way of the save.** A missing Directory node or entry logs a
  warning and the save goes through; saving again once they exist links them.
* **Not on raw saves.** loaddata replays rows as they are; fixtures carry
  their own graph.
* **One way to link.** `link_directory_owners` remains, for rows written
  without a save (`QuerySet.update`), and goes through the same function.
"""
import logging
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DIRECTORY = "owner-sync-dir"
OTHER = "owner-sync-other"


@pytest.fixture
async def graph(neo4j_graph):
    """Two Directory nodes and the organization's entry, not yet linked."""
    from neomodel import adb

    uids = {"entry": uuid.uuid4().hex, "dir": uuid.uuid4().hex, "other": uuid.uuid4().hex}
    await adb.cypher_query(
        """
        CREATE (:Directory {uid: $dir, name: $dir_name})
        CREATE (:Directory {uid: $other, name: $other_name})
        CREATE (:Entry {uid: $entry, active: true})
        """,
        {**uids, "dir_name": DIRECTORY, "other_name": OTHER},
    )
    return uids


@pytest.fixture
async def directories(site, transactional_db):
    from directory.models import Directory

    return {
        name: await Directory.objects.acreate(name=name, display_name=name, presentation="", site=site)
        for name in (DIRECTORY, OTHER)
    }


async def owners(directory_name):
    """Uids of the entries the directory is OWNED_BY."""
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        "MATCH (:Directory {name: $name})-[:OWNED_BY]->(e:Entry) RETURN e.uid",
        {"name": directory_name},
    )
    return sorted(row[0] for row in rows)


async def create_organization(**fields):
    from facility.models import Organization

    return await Organization.objects.acreate(name=f"org-{uuid.uuid4().hex[:8]}", **fields)


class TestSavingLinks:
    async def test_an_organization_saved_with_its_directory_owns_it(self, graph, directories):
        await create_organization(directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]))
        assert await owners(DIRECTORY) == [graph["entry"]]

    async def test_saving_again_adds_no_second_edge(self, graph, directories):
        org = await create_organization(directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]))
        await org.asave()
        assert await owners(DIRECTORY) == [graph["entry"]]

    async def test_a_directory_given_later_is_linked_then(self, graph, directories):
        org = await create_organization(neomodel_uid=uuid.UUID(graph["entry"]))
        assert await owners(DIRECTORY) == []
        org.directory = directories[DIRECTORY]
        await org.asave()
        assert await owners(DIRECTORY) == [graph["entry"]]

    async def test_an_entry_given_later_is_linked_then(self, graph, directories):
        org = await create_organization(directory=directories[DIRECTORY])
        assert await owners(DIRECTORY) == []
        org.neomodel_uid = uuid.UUID(graph["entry"])
        await org.asave()
        assert await owners(DIRECTORY) == [graph["entry"]]


class TestNothingToLink:
    async def test_a_missing_entry_does_not_stop_the_save(self, graph, directories, caplog):
        from facility.models import Organization

        missing = uuid.uuid4()
        with caplog.at_level(logging.WARNING):
            org = await create_organization(directory=directories[DIRECTORY], neomodel_uid=missing)
        assert await Organization.objects.filter(pk=org.pk).aexists()
        assert await owners(DIRECTORY) == []
        assert missing.hex in caplog.text

    async def test_a_missing_directory_node_does_not_stop_the_save(self, graph, site, transactional_db, caplog):
        from directory.models import Directory
        from facility.models import Organization

        only_in_django = await Directory.objects.acreate(
            name="owner-sync-django-only", display_name="owner-sync-django-only", presentation="", site=site,
        )
        with caplog.at_level(logging.WARNING):
            org = await create_organization(directory=only_in_django, neomodel_uid=uuid.UUID(graph["entry"]))
        assert await Organization.objects.filter(pk=org.pk).aexists()
        assert "owner-sync-django-only" in caplog.text

    async def test_a_raw_save_writes_nothing(self, graph, directories):
        # Created first: a raw save skips auto_now_add, as loaddata expects the
        # fixture to carry `created`.
        org = await create_organization()
        org.directory = directories[DIRECTORY]
        org.neomodel_uid = uuid.UUID(graph["entry"])
        await sync_to_async(org.save_base)(raw=True)
        assert await owners(DIRECTORY) == []


class TestOnlyAddNeverRemove:
    async def test_moving_to_another_directory_keeps_the_old_edge(self, graph, directories):
        """The old edge may be a second directory Django cannot describe."""
        org = await create_organization(directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]))
        org.directory = directories[OTHER]
        await org.asave()
        assert await owners(DIRECTORY) == [graph["entry"]]
        assert await owners(OTHER) == [graph["entry"]]

    async def test_clearing_the_directory_keeps_the_edge(self, graph, directories):
        org = await create_organization(directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]))
        org.directory = None
        await org.asave()
        assert await owners(DIRECTORY) == [graph["entry"]]


class TestTheCommand:
    async def test_links_what_a_queryset_update_left_unlinked(self, graph, directories):
        from facility.models import Organization

        org = await create_organization()
        await Organization.objects.filter(pk=org.pk).aupdate(
            directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]),
        )
        assert await owners(DIRECTORY) == []
        await sync_to_async(call_command)("link_directory_owners")
        assert await owners(DIRECTORY) == [graph["entry"]]

    async def test_running_it_twice_adds_no_second_edge(self, graph, directories):
        await create_organization(directory=directories[DIRECTORY], neomodel_uid=uuid.UUID(graph["entry"]))
        await sync_to_async(call_command)("link_directory_owners")
        await sync_to_async(call_command)("link_directory_owners")
        assert await owners(DIRECTORY) == [graph["entry"]]
