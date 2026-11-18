"""A Neo4j transaction belongs to the request that opened it.

neomodel 5 kept the open transaction on the process-wide `adb`, so while one
request was inside `async with adb.transaction:`, every other request's queries
ran in it too: on its connection, where two coroutines reading one socket
failed ("read() called while another coroutine is already waiting"), and
inside its rollback, which erased their writes. On 2026-10-11 the rollback
itself failed that way, the dead transaction stayed on `adb`, and every query
of the process answered "Transaction closed" until FastAPI restarted.

Each request is an asyncio task; here a task stands for each.
"""

import asyncio

import pytest
from neomodel import adb

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class RolledBack(Exception):
    pass


async def probes():
    rows, _ = await adb.cypher_query("MATCH (p:Probe) RETURN p.by ORDER BY p.by")
    return [by for (by,) in rows]


async def test_another_requests_write_survives_a_rollback(neo4j_graph):
    inside, release = asyncio.Event(), asyncio.Event()

    async def failing_request():
        async with adb.transaction:
            await adb.cypher_query("CREATE (:Probe {by: 'failing'})")
            inside.set()
            await release.wait()
            raise RolledBack

    request = asyncio.create_task(failing_request())
    await inside.wait()
    await adb.cypher_query("CREATE (:Probe {by: 'other'})")
    release.set()
    with pytest.raises(RolledBack):
        await request

    assert await probes() == ["other"]


async def test_another_request_does_not_see_uncommitted_writes(neo4j_graph):
    inside, release = asyncio.Event(), asyncio.Event()

    async def open_request():
        async with adb.transaction:
            await adb.cypher_query("CREATE (:Probe {by: 'uncommitted'})")
            inside.set()
            await release.wait()

    request = asyncio.create_task(open_request())
    await inside.wait()
    seen = await probes()
    release.set()
    await request

    assert seen == []
