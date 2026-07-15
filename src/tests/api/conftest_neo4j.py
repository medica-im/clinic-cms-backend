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
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def neo4j_container():
    """Session-scoped Neo4j 4.4 Enterprise container (the expensive part)."""
    from testcontainers.neo4j import Neo4jContainer

    container = (
        Neo4jContainer("neo4j:4.4-enterprise")
        .with_env("NEO4J_ACCEPT_LICENSE_AGREEMENT", "yes")
        .with_env("NEO4J_dbms_logs_query_enabled", "OFF")
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def neo4j_bolt_url(neo4j_container):
    """Bolt URL (with embedded credentials) for the session's container."""
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

    # parse "bolt://neo4j:pw@host:port" into (uri, auth) for the driver
    scheme, rest = neo4j_bolt_url.split("://", 1)
    creds, hostport = rest.split("@", 1)
    user, password = creds.split(":", 1)
    uri = f"{scheme}://{hostport}"

    original_url = neomodel_config.DATABASE_URL
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    await adb.set_connection(driver=driver)
    try:
        yield adb
    finally:
        await adb.close_connection()
        await driver.close()
        neomodel_config.DATABASE_URL = original_url


@pytest_asyncio.fixture
async def neo4j_graph(neo4j_connection):
    """Per-test clean graph: yields the live `adb`, wipes all nodes on teardown."""
    adb = neo4j_connection
    await adb.cypher_query("MATCH (n) DETACH DELETE n")
    try:
        yield adb
    finally:
        await adb.cypher_query("MATCH (n) DETACH DELETE n")
