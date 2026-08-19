"""Real-Neo4j integration fixtures.

Spins up a throwaway Neo4j 4.4 Enterprise container (matching production) via
testcontainers, repoints neomodel's async driver (`adb`) at it per test, and
wipes the graph between tests.

Requires the Docker socket to be reachable from wherever pytest runs (in this
repo the fastapi dev container mounts /var/run/docker.sock — see
docker-compose-development.yml).

These fixtures live in a separate module (imported by conftest.py) so the
testcontainers import is only paid for when an integration test actually pulls
in `neo4j_graph`.
"""
import logging
import os

import pytest
import pytest_asyncio


def _dev_neo4j_url() -> str | None:
    """The already-running Neo4j from docker-compose, if it is reachable.

    Reads the same NEO4J_* settings the application uses, so nothing has to be
    configured twice.
    """
    from django.conf import settings

    uri = getattr(settings, "NEO4J_URI", None)
    user = getattr(settings, "NEO4J_USERNAME", None)
    password = getattr(settings, "NEO4J_PASSWORD", None)
    if not (uri and user and password):
        return None
    scheme, hostport = uri.split("://", 1)
    # NEO4J_URI carries the *external* port (17687), the one published to the
    # host, while inside the compose network the server listens on 7687. The
    # application never notices because it connects through the same setting
    # from the same network, but a driver opened here does.
    host = hostport.split(":", 1)[0]
    port = os.environ.get("NEO4J_TEST_PORT", "7687")
    return f"{scheme}://{user}:{password}@{host}:{port}"


@pytest.fixture(scope="session")
def scratch_database(request):
    """A fresh, empty database on the Neo4j that is already running.

    Enterprise Edition can hold many databases side by side, so the suite does
    not need a container of its own: creating one costs ~1.4s against ~25s to
    start testcontainers, and dropping it afterwards leaves nothing behind.

    A *new* database each run, not a shared one — the dev container has a
    long-lived `test` database with 35k nodes in it, and asserting on counts
    against that would pass or fail for reasons unrelated to the code. APOC
    triggers are per-database too, so a scratch database also starts with none,
    which matters for the trigger tests.

    Yields None when the compose Neo4j is unreachable, and the container
    fixture takes over — which is what happens in CI.
    """
    from neo4j import GraphDatabase

    url = _dev_neo4j_url()
    if not url:
        return None

    scheme, rest = url.split("://", 1)
    creds, hostport = rest.split("@", 1)
    user, password = creds.split(":", 1)
    name = f"pytest{os.getpid()}"

    try:
        driver = GraphDatabase.driver(f"{scheme}://{hostport}", auth=(user, password))
        with driver.session(database="system") as session:
            session.run(f"CREATE DATABASE {name} WAIT")
    except Exception as e:  # noqa: BLE001 - fall back to the container
        logging.getLogger(__name__).info(
            "no scratch database (%s); falling back to testcontainers", e
        )
        return None

    def drop():
        with driver.session(database="system") as session:
            session.run(f"DROP DATABASE {name} IF EXISTS")
        driver.close()

    request.addfinalizer(drop)
    return f"{scheme}://{user}:{password}@{hostport}/{name}"


@pytest.fixture(scope="session")
def neo4j_container(scratch_database):
    """Session-scoped Neo4j 4.4 Enterprise container (the expensive part).

    Only started when scratch_database found no running Neo4j to borrow.
    """
    if scratch_database:
        yield None
        return
    from testcontainers.neo4j import Neo4jContainer

    container = (
        Neo4jContainer("neo4j:4.4-enterprise")
        .with_env("NEO4J_ACCEPT_LICENSE_AGREEMENT", "yes")
        .with_env("NEO4J_dbms_logs_query_enabled", "OFF")
        # APOC, because production runs with it and part of the schema is
        # implemented in it: directory/migrations/0028 installs four triggers
        # that maintain createdAt/updatedAt on every node. A container without
        # the plugin silently behaves differently from every real database.
        .with_env("NEO4JLABS_PLUGINS", '["apoc"]')
        .with_env("NEO4J_dbms_security_procedures_unrestricted", "apoc.*")
        .with_env("NEO4J_apoc_trigger_enabled", "true")
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def neo4j_bolt_url(scratch_database, neo4j_container):
    """Bolt URL (with embedded credentials) for whichever Neo4j we got."""
    if scratch_database:
        return scratch_database
    bolt_url = neo4j_container.get_connection_url()  # bolt://host:port
    password = neo4j_container.password
    scheme, rest = bolt_url.split("://", 1)
    return f"{scheme}://neo4j:{password}@{rest}"


@pytest_asyncio.fixture
async def neo4j_connection(neo4j_bolt_url):
    """Repoint neomodel's async `adb` at the container for one test.

    `adb` is a process-global connection shared by the whole app, and the neo4j
    async driver's sockets are event-loop-bound. This fixture is function-scoped
    like the rest of the suite, so the driver we create is bound to — and closed
    on — the same per-test loop the test runs on. We build the driver explicitly
    and hand it to neomodel via set_connection(driver=...) so we own its
    lifecycle and can close it inside this fixture's own loop, avoiding the
    "attached to a different loop" / "event loop is closed" errors that arise
    when a global async driver straddles pytest-asyncio's per-function loops.

    The original DATABASE_URL is restored on teardown so this doesn't leak into
    non-integration tests in the same run.
    """
    from neo4j import AsyncGraphDatabase
    from neomodel import adb, config as neomodel_config

    # parse "bolt://neo4j:pw@host:port[/database]" into (uri, auth, database)
    scheme, rest = neo4j_bolt_url.split("://", 1)
    creds, hostport = rest.split("@", 1)
    user, password = creds.split(":", 1)
    database = None
    if "/" in hostport:
        hostport, database = hostport.split("/", 1)
    uri = f"{scheme}://{hostport}"

    original_url = neomodel_config.DATABASE_URL
    original_database = getattr(neomodel_config, "DATABASE_NAME", None)
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    # The scratch database is not the server's default, so neomodel has to be
    # told which one to use; without this every query would run against the
    # dev graph.
    if database:
        neomodel_config.DATABASE_NAME = database
    await adb.set_connection(driver=driver)
    try:
        yield adb
    finally:
        await adb.close_connection()
        await driver.close()
        neomodel_config.DATABASE_URL = original_url
        if database:
            neomodel_config.DATABASE_NAME = original_database


@pytest_asyncio.fixture
async def neo4j_graph(neo4j_connection):
    """Per-test clean graph: yields the live `adb`, wipes all nodes on teardown."""
    adb = neo4j_connection
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    try:
        yield adb
    finally:
        await adb.cypher_query("MATCH (n) DETACH DELETE n")
