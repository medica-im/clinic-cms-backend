"""Requests share the process's Neo4j drivers.

neomodel 6 keeps its driver in a ContextVar, like the open transaction. A
server runs each request in a fresh copy of its root context, where no driver
was ever set, so neomodel built a new driver (and socket pool) per request and
never closed it: the dev FastAPI reached its 1024 open files during one BDD
run, and every request then failed.

The fixture behind these tests sets a driver in the test's own context, which
every in-process request inherits; that is why nothing else here caught it.
These requests run in an empty context instead, as a server's do.
"""

import asyncio
import contextvars
from unittest.mock import patch

import neo4j
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ROUTES = ["/api/v2/facilities-slug/no-such-place", "/api/v2/departments"]


@pytest.fixture
async def created_drivers():
    """Every driver neo4j hands out, closed afterwards so the test leaks none."""
    created = {"async": [], "sync": []}
    async_driver, sync_driver = neo4j.AsyncGraphDatabase.driver, neo4j.GraphDatabase.driver

    def counting(kind, make):
        def driver(*args, **kwargs):
            created[kind].append(made := make(*args, **kwargs))
            return made
        return driver

    with patch.object(neo4j.AsyncGraphDatabase, "driver", counting("async", async_driver)), \
         patch.object(neo4j.GraphDatabase, "driver", counting("sync", sync_driver)):
        yield created
    from api.neo4j_drivers import close_drivers

    await close_drivers()
    for driver in created["sync"]:
        driver.close()
    for driver in created["async"]:
        await driver.close()


async def test_requests_in_fresh_contexts_share_one_driver_each(
    neo4j_graph, versioned_client, created_drivers
):
    for _ in range(5):
        for route in ROUTES:
            request = versioned_client.get(route)
            response = await asyncio.create_task(request, context=contextvars.Context())
            assert response.status_code in (200, 404), (route, response.text)

    assert len(created_drivers["async"]) <= 1
    assert len(created_drivers["sync"]) <= 1
