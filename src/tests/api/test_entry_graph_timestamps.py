"""Graph edits stamp the node, and the database does it, not the application.

Four APOC triggers maintain `createdAt` and `updatedAt` on every node — see
directory/migrations/0028_neo4j_timestamp_triggers.py, which is where they are
declared and which installs them on every `manage.py migrate`.

This file exists because that arrangement is invisible from the Python source.
An earlier reading of the codebase concluded there was no writer for those
fields and that "the graph has no equivalent of Django's signals", and wired an
explicit `touch_entry` helper into three serializers to compensate. Both
conclusions were wrong: the triggers had been running all along, and the helper
duplicated them. It was removed, and these tests are what stands in its place —
they fail if the triggers stop being installed, which is the failure the helper
was mistakenly written to prevent.

The relationship pair is the part that is genuinely new. A relationship change
assigns no node property, so the two original triggers never fired for it: an
entry gaining a tag, joining an organisation or changing owner looked
untouched. Those are edits an owner makes from /e/{slug}, so the administrative
table reported them as unmodified.
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def triggers(neo4j_graph):
    """Install the migration's triggers into the throwaway test container.

    The fixture's Neo4j is a fresh container with an empty database, while the
    triggers are installed by a Django migration against the real one. Running
    the migration's own definitions here means these tests exercise the Cypher
    that ships, not a copy of it that could drift.
    """
    import importlib

    from neomodel import adb

    module = importlib.import_module(
        "directory.migrations.0028_neo4j_timestamp_triggers"
    )
    for name, query in module.TRIGGERS.items():
        await adb.cypher_query(
            "CALL apoc.trigger.add($name, $query, {phase: 'before'})",
            {"name": name, "query": query.strip()},
        )
    return module.TRIGGERS


async def _updated_at(uid: str):
    from neomodel import adb

    rows, _ = await adb.cypher_query(
        "MATCH (n:TimestampProbe {uid: $uid}) RETURN n.updatedAt", {"uid": uid}
    )
    return rows[0][0] if rows else None


class TestThePropertyTriggers:
    """What was already working, pinned so a lost trigger is noticed."""

    async def test_creating_a_node_stamps_it(self, triggers):
        from neomodel import adb

        await adb.cypher_query(
            "CREATE (n:TimestampProbe {uid: 'created', name: 'x'})"
        )

        rows, _ = await adb.cypher_query(
            "MATCH (n:TimestampProbe {uid: 'created'}) "
            "RETURN n.createdAt, n.updatedAt"
        )
        created, updated = rows[0]
        assert created is not None or updated is not None, (
            "neither createdAt nor updatedAt was set on a new node: the "
            "timestamp triggers are not installed"
        )

    async def test_changing_a_property_stamps_the_node(self, triggers):
        """The case the application never has to think about."""
        from neomodel import adb

        await adb.cypher_query(
            "CREATE (n:TimestampProbe {uid: 'prop', access: 'anonymous', updatedAt: 1})"
        )
        await adb.cypher_query(
            "MATCH (n:TimestampProbe {uid: 'prop'}) SET n.access = 'administrator'"
        )

        assert await _updated_at("prop") > 1


class TestTheRelationshipTriggers:
    """The gap the property triggers leave, and the reason 0028 exists.

    Tags, memberships, owners and directories are all relationship changes:
    they write no node property, so before these triggers the entry's
    updatedAt did not move and the administrative table showed it as
    unmodified after a real edit.
    """

    async def test_creating_a_relationship_stamps_both_ends(self, triggers):
        from neomodel import adb

        await adb.cypher_query(
            "CREATE (a:TimestampProbe {uid: 'rel-a', updatedAt: 1}), "
            "(b:TimestampProbe {uid: 'rel-b', updatedAt: 1})"
        )
        await adb.cypher_query(
            "MATCH (a:TimestampProbe {uid: 'rel-a'}), (b:TimestampProbe {uid: 'rel-b'}) "
            "MERGE (a)-[:MEMBER_OF]->(b)"
        )

        # Both ends, because either can be the entry: (entry)<-[:TAGS]- runs one
        # way and (entry)-[:MEMBER_OF]->(entry) the other.
        assert await _updated_at("rel-a") > 1
        assert await _updated_at("rel-b") > 1

    async def test_deleting_a_relationship_stamps_both_ends(self, triggers):
        """Removing a tag is an edit too, and the harder half to catch.

        The trigger has to run in `before` phase: in `after` the relationship
        is already gone and startNode() has nothing to return, so the stamp
        silently never happens.
        """
        from neomodel import adb

        await adb.cypher_query(
            "CREATE (a:TimestampProbe {uid: 'del-a'}), (b:TimestampProbe {uid: 'del-b'})"
        )
        await adb.cypher_query(
            "MATCH (a:TimestampProbe {uid: 'del-a'}), (b:TimestampProbe {uid: 'del-b'}) "
            "MERGE (a)-[:TAGS]->(b)"
        )
        await adb.cypher_query(
            "MATCH (n:TimestampProbe) WHERE n.uid IN ['del-a', 'del-b'] SET n.updatedAt = 1"
        )

        await adb.cypher_query(
            "MATCH (:TimestampProbe {uid: 'del-a'})-[r:TAGS]->(:TimestampProbe {uid: 'del-b'}) "
            "DELETE r"
        )

        assert await _updated_at("del-a") > 1
        assert await _updated_at("del-b") > 1


class TestTheTriggersAreDeclaredInAMigration:
    """The mechanism has to be visible in a checkout, not only in a database.

    Nothing in the source said these existed, so a reasonable reading of the
    code reached the opposite conclusion and added a redundant helper. The
    migration is what makes them reviewable; this test is what keeps the
    migration honest about which triggers the code assumes.
    """

    EXPECTED = {
        "create-timestamp",
        "update-insert-timestamp",
        "relationship-created-timestamp",
        "relationship-deleted-timestamp",
    }

    def test_the_migration_declares_every_trigger_the_code_relies_on(self):
        import importlib

        module = importlib.import_module(
            "directory.migrations.0028_neo4j_timestamp_triggers"
        )
        assert set(module.TRIGGERS) == self.EXPECTED
