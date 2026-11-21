"""The APOC triggers that maintain createdAt/updatedAt on every graph node.

Installed by directory/migrations/0028 and 0035, and by `manage.py
install_triggers` after a database is restored into an empty server, where the
migrations are already recorded as applied.

Neo4j 4.4 adds a trigger on the database itself with apoc.trigger.add, which
takes effect at once. Neo4j 5 installs it on the system database with
apoc.trigger.install, and the database picks it up at its next refresh
(apoc.trigger.refresh, 60 s by default), so install() waits for it.
"""
import time

from neo4j import GraphDatabase

# Every property write carries its own timestamp, so the application never has
# to. `before` phase, so the value lands in the same transaction as the change
# rather than as a second write after it.
CREATE_TIMESTAMP = """
UNWIND $createdNodes AS node
SET node.createdAt = timestamp()
"""

# $assignedNodeProperties maps each key to its list of updates. Indexed
# directly rather than through apoc.trigger.propertiesByKey, which APOC 5 no
# longer has; the result is the same on 4.4.
UPDATE_TIMESTAMP = """
UNWIND keys($assignedNodeProperties) AS key
UNWIND $assignedNodeProperties[key] AS update
WITH update.node AS node
SET node.updatedAt = timestamp()
"""

# The gap the two above leave, and the reason migration 0028 added these two.
#
# A relationship change assigns no node property, so neither trigger fires. An
# entry gaining a tag, joining an organisation, changing owner or moving
# directory looked untouched — and those are edits an owner or administrator
# makes from the entry page, so the administrative table reported them as
# unmodified. Verified rather than assumed: creating a relationship left
# updatedAt byte-identical before and after.
#
# Both endpoints are stamped because either can be the entry. (entry)<-[:TAGS]-
# runs one way and (entry)-[:MEMBER_OF]->(entry) the other; a trigger that
# picked one would miss half the cases.
RELATIONSHIP_CREATED_TIMESTAMP = """
UNWIND $createdRelationships AS rel
WITH [startNode(rel), endNode(rel)] AS nodes
UNWIND nodes AS node
SET node.updatedAt = timestamp()
"""

# `before` is required here, not stylistic: in `after` the relationship is
# already gone and startNode() has nothing to return. Confirmed against a live
# 4.4.48 database — the `after` form silently stamped nothing.
#
# The $deletedNodes guard is not defensive coding, it is required. A DETACH
# DELETE removes the relationship *and* its nodes in one transaction, so
# startNode() names something the trigger cannot load, and the whole
# transaction fails with "Unable to load NODE with id 0" — turning a legitimate
# delete into a 500. Stamping a node that is itself being deleted would be
# pointless anyway.
RELATIONSHIP_DELETED_TIMESTAMP = """
UNWIND $deletedRelationships AS rel
WITH [n IN [startNode(rel), endNode(rel)] WHERE NOT n IN $deletedNodes] AS nodes
UNWIND nodes AS node
SET node.updatedAt = timestamp()
"""

TRIGGERS = {
    "create-timestamp": CREATE_TIMESTAMP,
    "update-insert-timestamp": UPDATE_TIMESTAMP,
    "relationship-created-timestamp": RELATIONSHIP_CREATED_TIMESTAMP,
    "relationship-deleted-timestamp": RELATIONSHIP_DELETED_TIMESTAMP,
}

# Longer than apoc.trigger.refresh's default of 60 s.
ACTIVATION_TIMEOUT = 90


def _connection():
    """URI, credentials and database from neomodel's configuration."""
    from django.conf import settings

    from api.neo4j_drivers import _target

    uri, auth, database = _target()
    return uri, auth, database or settings.NEO4J_DATABASE


def _major_version(driver, database) -> int:
    with driver.session(database=database) as session:
        version = session.run(
            "CALL dbms.components() YIELD versions RETURN versions[0]"
        ).single()[0]
    return int(version.split(".")[0])


def _active(driver, database) -> set[str]:
    with driver.session(database=database) as session:
        return {
            record["name"]
            for record in session.run("CALL apoc.trigger.list() YIELD name")
        }


def install(names=None) -> None:
    """Install the named triggers (all by default), replacing any of the same name."""
    names = list(names or TRIGGERS)
    uri, auth, database = _connection()
    with GraphDatabase.driver(uri, auth=auth) as driver:
        if _major_version(driver, database) < 5:
            with driver.session(database=database) as session:
                for name in names:
                    session.run(
                        "CALL apoc.trigger.add($name, $query, {phase: 'before'})",
                        {"name": name, "query": TRIGGERS[name].strip()},
                    ).consume()
            return
        with driver.session(database="system") as session:
            for name in names:
                session.run(
                    "CALL apoc.trigger.install($database, $name, $query, {phase: 'before'})",
                    {"database": database, "name": name, "query": TRIGGERS[name].strip()},
                ).consume()
        deadline = time.monotonic() + ACTIVATION_TIMEOUT
        while not set(names) <= _active(driver, database):
            if time.monotonic() > deadline:
                missing = set(names) - _active(driver, database)
                raise RuntimeError(f"triggers not active after {ACTIVATION_TIMEOUT}s: {sorted(missing)}")
            time.sleep(1)


def remove(names) -> None:
    uri, auth, database = _connection()
    with GraphDatabase.driver(uri, auth=auth) as driver:
        if _major_version(driver, database) < 5:
            with driver.session(database=database) as session:
                for name in names:
                    session.run("CALL apoc.trigger.remove($name)", {"name": name}).consume()
            return
        with driver.session(database="system") as session:
            for name in names:
                session.run(
                    "CALL apoc.trigger.drop($database, $name)",
                    {"database": database, "name": name},
                ).consume()
